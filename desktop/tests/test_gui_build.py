"""Construct our own hidden Tk window; no OS automation, capture or live APIs."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.app import App
from desktop.memory import ProfileStore


@unittest.skipUnless(sys.platform == "win32", "Windows Tk integration")
class GuiBuildTests(unittest.TestCase):
    def test_profile_selection_clears_previous_friend_context(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles.json")
            a, b = store.create("Alice"), store.create("Bob")
            root = tk.Tk()
            root.withdraw()
            try:
                with patch("desktop.app.ProfileStore", return_value=store):
                    app = App(root, {"MINERU_API_TOKEN": "", "DEEPSEEK_API_KEY": "", "TYPESAFE_API_KEY": ""})
                app.select_contact(a)
                app.set_transcript("对方：Alice private context")
                app.relationship.set("Alice-specific relationship")
                app.select_contact(b)
                self.assertEqual(app.transcript.get("1.0", "end").strip(), "")
                self.assertEqual(app.relationship.get(), "")
                self.assertEqual(app.contact_id, b)
                root.update_idletasks()
                self.assertEqual(len(app.contact_combo["values"]), 3)
            finally:
                root.destroy()
