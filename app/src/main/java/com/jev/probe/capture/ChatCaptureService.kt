package com.jev.probe.capture

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.graphics.Rect
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.jev.probe.capture.ocr.MlKitOcr
import com.jev.probe.capture.ocr.OcrLine
import com.jev.probe.capture.ocr.ScreenCapture
import com.jev.probe.core.AnalysisSession
import com.jev.probe.core.Analysis
import com.jev.probe.core.RankedReply
import com.jev.probe.core.BubbleRect
import com.jev.probe.core.ChatSnapshot
import com.jev.probe.core.Msg
import com.jev.probe.core.Prefs
import com.jev.probe.core.kb.ContextBuilder
import com.jev.probe.core.kb.KbStore
import com.jev.probe.jev.JevClient
import com.jev.probe.overlay.OverlayController
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException

/**
 * The live capture service (registered under a disguised class name so WeChat
 * exposes its node tree — see the disguised subclass). It reads whichever
 * adapted chat app is in the foreground, detects a new incoming message from the
 * other person, runs Jev analysis off the main thread, and drives the floating
 * overlay.
 *
 * Per-app node rules live in [ChatAppAdapter] implementations; everything here
 * is app-agnostic.
 *
 * It never sends a message. The only write action is ACTION_SET_TEXT (or a
 * clipboard PASTE fallback) to fill the chat input box when the user taps
 * "填入"; the user still presses send.
 */
open class ChatCaptureService : AccessibilityService() {

    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newFixedThreadPool(2)

    /** Adapted chat apps, keyed by package name. */
    private val adapters = listOf(WeChatAdapter(), QQAdapter(), XAdapter(), FeishuAdapter()).associateBy { it.pkg }

    /** Submit to the worker, ignoring rejection after the service is torn down
     *  (a stale overlay callback must never crash the process). */
    private fun submit(task: () -> Unit) {
        try { worker.execute(task) } catch (_: RejectedExecutionException) { }
    }
    private lateinit var prefs: Prefs
    private var overlay: OverlayController? = null

    private val session = AnalysisSession()
    private var destroyed = false
    private var activePkg: String? = null
    private var currentSnapshot: ChatSnapshot? = null
    private val debounce = Runnable { runAnalysis() }

    private fun clearSession() {
        session.invalidate()
        main.removeCallbacks(debounce)
        currentSnapshot = null
        activePkg = null
        lastOcrSignature = ""
        overlay?.resetForNewConversation()
    }

    private fun conversationKey(root: AccessibilityNodeInfo, title: String?): String =
        "${root.packageName}:${root.windowId}:${title?.trim().orEmpty()}"

    private fun sourceSignature(pkg: String, snapshot: ChatSnapshot): String =
        if (snapshot.messages.isEmpty()) "ocr:" + ocrSignature(pkg, snapshot.title, snapshot.bubbleRects)
        else snapshot.signature()

    private fun observe(root: AccessibilityNodeInfo, snapshot: ChatSnapshot, signature: String): AnalysisSession.Ticket {
        val before = session.current
        val ticket = session.observe(conversationKey(root, snapshot.title), signature)
        activePkg = root.packageName?.toString()
        if (before != ticket) {
            main.removeCallbacks(debounce)
            currentSnapshot = null
            overlay?.resetForNewConversation()
        }
        return ticket
    }

    /** Re-read the active window as events may still be waiting in the queue. */
    private fun isLive(ticket: AnalysisSession.Ticket): Boolean {
        if (destroyed || !prefs.enabled || !session.isCurrent(ticket)) return false
        val root = rootInActiveWindow ?: return false
        val pkg = root.packageName?.toString() ?: return false
        val adapter = adapters[pkg]
        if (adapter == null) return ticket.signature == "manual" &&
            ticket.conversation == conversationKey(root, null)
        val snapshot = adapter.extract(root, resources) ?: return false
        return !isTransientTitle(snapshot.title) && prefs.isAllowed(snapshot.title) &&
            ticket.conversation == conversationKey(root, snapshot.title) &&
            ticket.signature == sourceSignature(pkg, snapshot)
    }

    // ---- OCR path (B stage). Everything here runs on the main thread: the
    // screenshot callback and the ML Kit callback are both posted back to it.
    private val screenCapture by lazy {
        ScreenCapture(this,
            hideOverlay = { overlay?.setHiddenForShot(true) },
            restoreOverlay = { overlay?.setHiddenForShot(false) })
    }
    private val ocr = MlKitOcr()
    private var ocrBusy = false

    /** What the screen looked like the last time we fired an automatic shot.
     *  See [ocrSignature]: this is the brake on the OCR path. */
    private var lastOcrSignature: String = ""

    override fun onServiceConnected() {
        super.onServiceConnected()
        prefs = Prefs(this)
        overlay = OverlayController(this)
        overlay?.onManualAnalyze = {
            val ticket = session.current
            if (ticket != null && isLive(ticket)) runAnalysis()
            else { clearSession(); maybeCapture() }
        }
        // Bubble menu: file the open conversation as a knowledge-base contact.
        // Contacts are never created automatically — this is the one-tap way in.
        overlay?.onSaveContact = {
            val title = currentSnapshot?.title
            val pkg = activePkg ?: ""
            when {
                session.current?.let { isLive(it) } != true -> overlay?.toast("会话已变化，请重新读取")
                title.isNullOrBlank() -> overlay?.toast("当前会话没有标题，存不了")
                isTransientTitle(title) -> overlay?.toast("当前会话标题还没加载出来，稍后再试")
                else -> submit {
                    val msg = try {
                        KbStore.get(this).saveOrMergeContact(title, pkg)
                    } catch (e: Exception) { "保存失败：${e.javaClass.simpleName}" }
                    main.post { overlay?.toast(msg) }
                }
            }
        }
        // Bubble menu: one manual screenshot + OCR, for any app at all.
        overlay?.onOcrCapture = { ocrCaptureManual() }
        // Keep the process at foreground importance so MIUI does not freeze us.
        runCatching { KeepAliveService.start(this) }
        // Load the bundled OCR model now, off the main thread: the first
        // recognize() otherwise pays for it inside the screenshot callback.
        submit { MlKitOcr.warmUp() }
        // HyperOS may kill and restart us. On (re)connect, proactively re-show the
        // bubble for whatever chat is already open, so it comes back on its own
        // instead of waiting for the user to scroll.
        main.postDelayed({ if (prefs.enabled) runCatching { maybeCapture() } }, 900)
        Log.i(TAG, "capture service connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null || destroyed || !::prefs.isInitialized) return
        if (!prefs.enabled) { clearSession(); overlay?.hide(); return }
        when (event.eventType) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED,
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED,
            AccessibilityEvent.TYPE_VIEW_SCROLLED -> {
                val root = rootInActiveWindow
                val pkg = root?.packageName?.toString()
                if (pkg !in adapters) {
                    // Unsupported apps remain available for explicit OCR only.
                    if (activePkg != pkg || event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
                        clearSession()
                        val drop = pkg == null || pkg == packageName ||
                            pkg.contains("launcher", true) || pkg == "com.miui.home" || pkg == "com.android.systemui"
                        if (drop) overlay?.hide() else overlay?.showIdle(null)
                    }
                    return
                }
                maybeCapture()
            }
        }
    }

    private fun maybeCapture() {
        if (destroyed || !prefs.enabled) return
        val root = rootInActiveWindow ?: run { clearSession(); overlay?.hide(); return }
        val pkg = root.packageName?.toString() ?: return
        val adapter = adapters[pkg] ?: return
        val snapshot = adapter.extract(root, resources)
        // Never borrow the previous contact's title during a loading transition.
        if (snapshot == null || isTransientTitle(snapshot.title) || !prefs.isAllowed(snapshot.title)) {
            clearSession(); overlay?.hide(); return
        }
        val before = session.current
        val ticket = observe(root, snapshot, sourceSignature(pkg, snapshot))
        if (snapshot.messages.isEmpty()) {
            if (prefs.ocrFallback && !ocrBusy) {
                if (lastOcrSignature == ticket.toString() && overlay?.isShowing() == true) return
                lastOcrSignature = ticket.toString()
                ocrCapture(snapshot.title, snapshot.bubbleRects, pkg, manual = false, ticket = ticket)
            }
            return
        }
        currentSnapshot = snapshot
        if (before == ticket) {
            if (overlay?.isShowing() != true) overlay?.showIdle(snapshot.title)
            return
        }
        Log.d(TAG, "snapshot[$pkg] n=${snapshot.messages.size}")
        overlay?.showIdle(snapshot.title)
        if (snapshot.latestFrom == "other" && prefs.autoAnalyze) main.postDelayed(debounce, 800)
    }

    /** A placeholder title an app shows only for a moment (e.g. X's "连接中…"
     *  right after opening a DM thread) — never a real conversation title.
     *  Blank/null counts too, so a caller can always fall back the same way. */
    private fun isTransientTitle(t: String?): Boolean {
        val trimmed = t?.trim()?.removeSuffix("…")?.removeSuffix("...")?.trim()
        if (trimmed.isNullOrEmpty()) return true
        val lower = trimmed.lowercase()
        return TRANSIENT_TITLE_WORDS.any { lower.contains(it.lowercase()) }
    }

    private fun runAnalysis() {
        val ticket = session.current ?: return
        if (!isLive(ticket) || currentSnapshot == null) return
        if (!prefs.hasKey()) { overlay?.showError("未设置判断接口密钥，去设置里填"); return }
        session.request()
        drainAnalysis()
    }

    private fun drainAnalysis() {
        val ticket = session.startNext() ?: return
        val snapshot = currentSnapshot
        if (snapshot == null || !isLive(ticket)) { session.finish(ticket); return }
        val pkg = activePkg ?: ""
        val client = JevClient(prefs)
        val rel = prefs.relationship
        overlay?.showLoading()
        overlay?.setNote(snapshot.note)
        // These completion fields are accessed only on the main thread.
        var judgment: Analysis? = null
        var replies: List<RankedReply> = emptyList()
        var replyError: String? = null
        var completed = 0
        fun completeBranch() {
            completed++
            if (completed != 2) return
            if (isLive(ticket)) {
                val a = judgment
                if (a?.error != null) overlay?.showError(a.error)
                else if (a != null) {
                    // Replies may arrive first; always render after the judgment.
                    overlay?.showJudgment(a)
                    overlay?.showReplies(replies, replyError) { text -> fillInput(text, ticket) }
                }
            }
            session.finish(ticket)
            drainAnalysis() // The newest pending screen is never lost.
        }
        submit {
            val ctx = try { ContextBuilder.build(this, snapshot, pkg, prefs) }
                catch (e: Exception) { Log.w(TAG, "context build failed: ${e.javaClass.simpleName}"); null }
            main.post { if (isLive(ticket)) overlay?.setContextInfo(ctx?.notes?.size ?: 0, ctx?.history?.size ?: 0) }
            submit {
                val result = client.judge(snapshot, rel, ctx)
                main.post {
                    judgment = result
                    if (isLive(ticket) && result.error == null) overlay?.showJudgment(result)
                    completeBranch()
                }
            }
            submit {
                var error: String? = null
                val result = try { client.draftAndRank(snapshot, rel, ctx) }
                    catch (e: Exception) { error = e.message ?: e.javaClass.simpleName; emptyList() }
                main.post { replies = result; replyError = error; completeBranch() }
            }
        }
    }

    // ------------------------------------------------------------------ OCR

    /**
     * Bubble menu → "截屏识别一次". Works on ANY app, adapted or not: one whole
     * screen shot, every line OCR'd, lines grouped into pseudo-bubbles by line
     * spacing. Nobody can tell who said what this way, so everything is filed as
     * the other person and the panel says so.
     */
    private fun ocrCaptureManual() {
        if (destroyed || !prefs.enabled || ocrBusy) return
        val root = rootInActiveWindow ?: return
        val pkg = root.packageName?.toString() ?: return
        val adapter = adapters[pkg]
        val snapshot = if (adapter == null) ChatSnapshot(null, emptyList())
            else adapter.extract(root, resources) ?: return
        if (adapter != null && isTransientTitle(snapshot.title)) return
        if (!prefs.isAllowed(snapshot.title)) return
        val ticket = observe(root, snapshot, if (adapter == null) "manual" else sourceSignature(pkg, snapshot))
        ocrCapture(snapshot.title, emptyList(), pkg, manual = true, ticket = ticket)
    }

    /**
     * What the screen would look like to a camera, as far as the tree can tell.
     *
     * Feishu: the conversation title plus every bubble rectangle and its side —
     * the bubbles move whenever the list scrolls or a message arrives, and stay
     * put when only chrome (caret, presence dot, timestamp) redraws. Apps that
     * give us no rectangles fall back to package + title, which at least stops a
     * burst of events on one screen from becoming a burst of screenshots.
     */
    private fun ocrSignature(pkg: String, title: String?, rects: List<BubbleRect>): String {
        if (rects.isEmpty()) return pkg + "|" + (title ?: "")
        return (title ?: "") + "|" + rects.joinToString(";") { br ->
            val r = br.rect
            "${r.left},${r.top},${r.right},${r.bottom},${br.side}"
        }
    }

    /**
     * Screenshot, then either OCR each known bubble rect (Feishu: the tree knows
     * where the bubbles are and who sent them, just not what they say) or OCR
     * the whole screen (everything else).
     */
    private fun ocrCapture(treeTitle: String?, rects: List<BubbleRect>, pkg: String, manual: Boolean, ticket: AnalysisSession.Ticket) {
        if (ocrBusy) return
        ocrBusy = true
        screenCapture.capture { res ->
            if (!isLive(ticket)) {
                if (res is ScreenCapture.Result.Ok) res.bitmap.recycle()
                ocrBusy = false
                lastOcrSignature = ""
                maybeCapture()
                return@capture
            }
            when (res) {
                is ScreenCapture.Result.Failed -> {
                    ocrBusy = false
                    Log.i(TAG, "ocr: screenshot failed code=${res.code}")
                    // Nothing was read, so the signature must not claim this screen
                    // is done — the next event may retry, still held back by
                    // ScreenCapture's own throttle and failure backoff.
                    if (!manual) lastOcrSignature = ""
                    // Throttle/interval codes are transient timing, not something
                    // the user can act on — nagging about them would be constant.
                    val transient = res.code == ScreenCapture.CODE_THROTTLED || res.code == 3
                    if (manual || !transient) overlay?.showError(res.humanMessage)
                }
                is ScreenCapture.Result.Ok -> {
                    ocr.scaleX = res.scaleX; ocr.scaleY = res.scaleY
                    ocr.originX = res.originX; ocr.originY = res.originY
                    if (rects.isNotEmpty() && !manual) {
                        // Re-measure inside the callback. The rects handed in were
                        // read before the 120ms overlay-hide wait and the shot
                        // itself; one scroll tick in between and we would crop the
                        // rows next to the ones in the picture. Fall back to the
                        // old rects only if the tree gives us nothing now.
                        val fresh = rootInActiveWindow?.let { collectFeishuBubbleRects(it, resources) }
                        ocrByRects(res.bitmap, if (fresh.isNullOrEmpty()) rects else fresh, treeTitle, pkg, ticket)
                    } else ocrWholeScreen(res.bitmap, treeTitle, pkg, manual, ticket)
                }
            }
        }
    }

    /** One OCR pass per bubble rectangle; each rect becomes exactly one message. */
    private fun ocrByRects(bmp: Bitmap, rects: List<BubbleRect>, title: String?, pkg: String, ticket: AnalysisSession.Ticket) {
        val sx = ocr.scaleX; val sy = ocr.scaleY
        // Screen -> bitmap: drop the window origin first. A window shot does not
        // start at (0,0) in split screen or when it excludes the status bar.
        val ox = ocr.originX; val oy = ocr.originY
        val out = arrayOfNulls<Msg>(rects.size)
        var remaining = rects.size
        rects.forEachIndexed { i, br ->
            val region = Rect(
                ((br.rect.left - ox) * sx).toInt(), ((br.rect.top - oy) * sy).toInt(),
                ((br.rect.right - ox) * sx).toInt(), ((br.rect.bottom - oy) * sy).toInt())
            ocr.recognize(bmp, region) { lines ->
                val text = cleanBubbleText(lines.joinToString(" ") { it.text })
                if (text.isNotEmpty()) out[i] = Msg(br.side, text)
                remaining--
                if (remaining == 0) {
                    runCatching { bmp.recycle() }
                    finishOcrSnapshot(ChatSnapshot(title, out.filterNotNull()), pkg, manual = false, ticket = ticket)
                }
            }
        }
    }

    /** Whole screen minus the top bar and the input area, grouped by line gaps. */
    private fun ocrWholeScreen(bmp: Bitmap, treeTitle: String?, pkg: String, manual: Boolean, ticket: AnalysisSession.Ticket) {
        val region = Rect(0, (bmp.height * TOP_CROP).toInt(), bmp.width, (bmp.height * BOTTOM_CROP).toInt())
        ocr.recognize(bmp, region) { lines ->
            runCatching { bmp.recycle() }
            val msgs = groupOcrLines(lines)
            // OCR message text is never a contact identity.
            finishOcrSnapshot(ChatSnapshot(treeTitle, msgs, note = OCR_NOTE), pkg, manual, ticket)
        }
    }

    /**
     * OCR lines → "bubbles": a gap larger than 1.2x the previous line's height
     * starts a new one. Side is unknowable from a flat screen read, so every
     * group is filed as the other person (and [OCR_NOTE] says so on the panel).
     */
    private fun groupOcrLines(lines: List<OcrLine>): List<Msg> {
        val usable = lines
            .filter { it.text.isNotBlank() && !PURE_TIME.matches(it.text.trim()) }
            .sortedBy { it.bounds.top }
        val out = ArrayList<Msg>()
        val buf = StringBuilder()
        var prev: OcrLine? = null
        for (l in usable) {
            val p = prev
            if (p != null) {
                val gap = l.bounds.top - p.bounds.bottom
                val lineHeight = maxOf(p.bounds.height(), 1)
                if (gap > lineHeight * 1.2f) {
                    if (buf.isNotEmpty()) { out.add(Msg("other", buf.toString())); buf.setLength(0) }
                }
            }
            if (buf.isNotEmpty()) buf.append(' ')
            buf.append(l.text.trim())
            prev = l
        }
        if (buf.isNotEmpty()) out.add(Msg("other", buf.toString()))
        return out
    }

    /** Strip the read receipt and the timestamp Feishu glues onto a bubble. */
    private fun cleanBubbleText(raw: String): String {
        var t = raw.trim()
        var changed = true
        while (changed && t.isNotEmpty()) {
            changed = false
            for (tail in arrayOf("已读", "未读")) {
                if (t.endsWith(tail)) { t = t.removeSuffix(tail).trim(); changed = true }
            }
            TAIL_TIME.find(t)?.let { t = t.substring(0, it.range.first).trim(); changed = true }
        }
        return t
    }

    /** Shared tail of both OCR paths: dedupe, then analyze or park the bubble. */
    private fun finishOcrSnapshot(snapshot: ChatSnapshot, pkg: String, manual: Boolean, ticket: AnalysisSession.Ticket) {
        ocrBusy = false
        if (!isLive(ticket)) { lastOcrSignature = ""; maybeCapture(); return }
        Log.i(TAG, "ocr[$pkg] msgs=${snapshot.messages.size} manual=$manual")
        if (snapshot.messages.isEmpty()) {
            lastOcrSignature = ""
            if (manual) overlay?.showError("这一屏没认出文字")
            return
        }
        currentSnapshot = snapshot
        overlay?.resetForNewConversation()
        overlay?.setNote(snapshot.note)
        overlay?.showIdle(snapshot.title)
        if (manual || (prefs.ocrAutoAnalyze && prefs.autoAnalyze && snapshot.latestFrom == "other")) runAnalysis()
    }

    /** Fill the chat input box with the chosen reply (never sends). */
    private fun fillInput(text: String, ticket: AnalysisSession.Ticket) {
        // All UI reads and writes run on the main thread. Delayed retries must
        // validate again, since the user can switch chats while the IME opens.
        fun target(): AccessibilityNodeInfo? {
            if (!isLive(ticket)) return null
            val root = rootInActiveWindow ?: return null
            if (root.packageName?.toString() !in adapters) return null
            // OCR cannot verify that the text has stayed unchanged. Copy only.
            if (ticket.signature.startsWith("ocr:") || ticket.signature == "manual") return null
            return findEditable(root)
        }
        val edit = target()
        if (edit == null) {
            if (isLive(ticket)) { copyToClipboard(text); overlay?.toast("无法核验当前输入框，已复制，请手动粘贴") }
            else overlay?.toast("会话或消息已变化，请重新分析后填入")
            return
        }
        if (!edit.text.isNullOrBlank() && edit.text.toString() != text) {
            copyToClipboard(text)
            overlay?.toast("输入框已有草稿，已复制候选，请自行合并")
            return
        }
        setTextRaw(edit, text)
        main.postDelayed({
            val now = target()
            if (now == null) { overlay?.toast("会话已变化，已停止填入"); return@postDelayed }
            if (now.text?.toString() == text) { overlay?.toast("已填入，确认后自己发送"); return@postDelayed }
            if (!now.text.isNullOrBlank()) {
                copyToClipboard(text); overlay?.toast("输入框已有内容，已复制候选"); return@postDelayed
            }
            now.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            main.postDelayed({
                val focused = target()
                if (focused == null) { overlay?.toast("会话已变化，已停止填入"); return@postDelayed }
                if (!focused.text.isNullOrBlank()) {
                    copyToClipboard(text); overlay?.toast("输入框已有内容，已复制候选"); return@postDelayed
                }
                copyToClipboard(text)
                focused.performAction(AccessibilityNodeInfo.ACTION_PASTE)
                main.postDelayed({
                    val after = target()
                    if (after?.text?.toString() == text) overlay?.toast("已填入，确认后自己发送")
                    else overlay?.toast("已复制候选，请检查输入框后手动粘贴")
                }, 150)
            }, 300)
        }, 150)
    }

    private fun setTextRaw(edit: AccessibilityNodeInfo, text: String): Boolean {
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return edit.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    private fun findEditable(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val stack = ArrayDeque<AccessibilityNodeInfo>()
        stack.addLast(root)
        var guard = 0
        while (stack.isNotEmpty() && guard < 5000) {
            guard++
            val node = stack.removeLast()
            if (node.isEditable) return node
            for (i in node.childCount - 1 downTo 0) node.getChild(i)?.let { stack.addLast(it) }
        }
        return null
    }

    private fun copyToClipboard(text: String) {
        val cm = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
        cm.setPrimaryClip(android.content.ClipData.newPlainText("jev_reply", text))
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        destroyed = true
        clearSession()
        main.removeCallbacksAndMessages(null)
        super.onDestroy()
        // Tear the overlay down and cut its callback so a stale button tap can
        // never call back into this dead instance.
        overlay?.onManualAnalyze = null
        overlay?.onSaveContact = null
        overlay?.onOcrCapture = null
        overlay?.hide()
        overlay = null
        worker.shutdownNow()
    }

    companion object {
        private const val TAG = "JEVASSIST"

        /** Whole-screen OCR keeps the middle: no action bar, no input area. */
        private const val TOP_CROP = 0.12f
        private const val BOTTOM_CROP = 0.84f

        /** Said on the panel whenever a snapshot came from flat-screen OCR. */
        private const val OCR_NOTE = "OCR 未分边，把全部消息当作对方所说"

        private val PURE_TIME = Regex("""\d{1,2}[:：]\d{2}""")
        private val TAIL_TIME = Regex("""\d{1,2}[:：]\d{2}$""")

        /** Transient placeholder titles apps show while a chat page is still
         *  connecting/loading — see [isTransientTitle]. Matched as a substring,
         *  case-insensitive, after trimming a trailing ellipsis. */
        private val TRANSIENT_TITLE_WORDS = listOf(
            "连接中", "正在连接", "未连接", "Connecting",
            "加载中", "Loading", "同步中", "Syncing"
        )
    }
}
