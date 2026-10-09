import unittest
from ad_host.commands import encode_command


class CommandTests(unittest.TestCase):
    def test_exact_bytes_and_suffix(self):
        self.assertEqual(encode_command("AA 55\n00 ff"), b"\xaa\x55\x00\xff")
        self.assertEqual(encode_command("开始", "UTF-8", "CRLF"), "开始\r\n".encode())
        self.assertEqual(encode_command("00", "HEX", "LF"), b"\x00\n")

    def test_reject_bad_commands(self):
        for value in ("", "A", "GG", "0xAA", "AA,55"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                encode_command(value)
        with self.assertRaises(ValueError):
            encode_command("AA" * 4097)
        with self.assertRaises(ValueError):
            encode_command("x", "UTF-8", "invalid")
