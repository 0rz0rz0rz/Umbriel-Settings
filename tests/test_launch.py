import unittest

from umbriel_config_gui.launch import child_env, terminal_command


class ChildEnvTests(unittest.TestCase):
    def test_outside_appimage_environment_is_unchanged(self):
        environ = {"PYTHONPATH": "/host", "HOME": "/home/user"}
        self.assertEqual(child_env(environ), environ)

    def test_appimage_restores_host_python_variables(self):
        environ = {
            "UMBRIEL_GUI_APPIMAGE_ENV": "1",
            "PYTHONPATH": "/tmp/.mount_app",
            "PYTHONNOUSERSITE": "1",
            "UMBRIEL_GUI_HOST_PYTHONPATH": "/host/lib",
            "HOME": "/home/user",
        }
        env = child_env(environ)
        self.assertEqual(env["PYTHONPATH"], "/host/lib")
        self.assertNotIn("PYTHONNOUSERSITE", env)
        self.assertEqual(env["HOME"], "/home/user")
        self.assertFalse(any(name.startswith("UMBRIEL_GUI_") for name in env))


class TerminalCommandTests(unittest.TestCase):
    def test_uses_each_terminals_command_syntax(self):
        argv = ["nvim", "/cfg/config.toml"]
        self.assertEqual(terminal_command("/usr/bin/kitty", argv), ["/usr/bin/kitty", *argv])
        self.assertEqual(terminal_command("/usr/bin/foot", argv), ["/usr/bin/foot", *argv])
        self.assertEqual(terminal_command("/usr/bin/gnome-terminal", argv), ["/usr/bin/gnome-terminal", "--", *argv])
        self.assertEqual(terminal_command("/usr/bin/konsole", argv), ["/usr/bin/konsole", "-e", *argv])


if __name__ == "__main__":
    unittest.main()
