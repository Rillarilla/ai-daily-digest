import io
import smtplib
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, patch

import main
from email_sender import EmailSender


class EmailSenderTest(unittest.TestCase):
    def send(self, port):
        sender = EmailSender(smtp_port=port, smtp_user="sender@example.com", smtp_password="test")
        with redirect_stdout(io.StringIO()) as output:
            result = sender.send("reader@example.com", "Digest", "<p>News</p>")
        return result, output.getvalue()

    @patch("email_sender.smtplib.SMTP")
    @patch("email_sender.smtplib.SMTP_SSL")
    def test_port_465_uses_implicit_tls(self, smtp_ssl, smtp):
        result, _ = self.send(465)
        self.assertTrue(result)
        smtp.assert_not_called()
        server = smtp_ssl.return_value.__enter__.return_value
        server.starttls.assert_not_called()
        server.login.assert_called_once()
        server.sendmail.assert_called_once()

    @patch("email_sender.smtplib.SMTP")
    def test_port_587_negotiates_tls_before_login(self, smtp):
        result, _ = self.send(587)
        self.assertTrue(result)
        server = smtp.return_value.__enter__.return_value
        self.assertEqual([call[0] for call in server.method_calls], ["starttls", "login", "sendmail"])

    @patch("email_sender.smtplib.SMTP_SSL")
    def test_authentication_disconnect_is_reported_without_sending(self, smtp_ssl):
        server = smtp_ssl.return_value.__enter__.return_value
        server.login.side_effect = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        result, output = self.send(465)
        self.assertFalse(result)
        self.assertIn("SMTP authentication failed", output)
        server.sendmail.assert_not_called()

    @patch("email_sender.smtplib.SMTP_SSL")
    def test_quit_error_does_not_mark_an_accepted_message_as_failed(self, smtp_ssl):
        smtp_ssl.return_value.__exit__.side_effect = smtplib.SMTPResponseException(421, b"Closing")
        result, output = self.send(465)
        self.assertTrue(result)
        self.assertIn("after delivery", output)


class DailyDigestDeliveryTest(unittest.IsolatedAsyncioTestCase):
    @patch("main.FeishuPublisher")
    @patch("main.EmailSender")
    @patch("main.WEASYPRINT_AVAILABLE", False)
    @patch("main.GeminiSummarizer", side_effect=RuntimeError("Disabled during test"))
    @patch("main.process_items", return_value={})
    @patch("main.collect_all_sources", new_callable=AsyncMock, return_value=[object()])
    async def test_email_result_controls_run_status_without_feishu(self, _, __, ___, sender, feishu):
        for sent, expected in ((True, 0), (False, 1)):
            with self.subTest(sent=sent), redirect_stdout(io.StringIO()):
                sender.return_value.send.return_value = sent
                self.assertEqual(await main.main_async(), expected)
        feishu.assert_not_called()
