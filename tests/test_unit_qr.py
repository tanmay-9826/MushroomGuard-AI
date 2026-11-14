import unittest
from io import BytesIO

from services.unit_qr import decode_unit_qr_from_jpeg, parse_unit_qr_payload, stage_name


class UnitQrTests(unittest.TestCase):
    def test_canonical_qr_payload(self):
        self.assertEqual(parse_unit_qr_payload("MUSHROOMGUARD:MICRO-00001"), "MICRO-00001")

    def test_plain_unit_id(self):
        self.assertEqual(parse_unit_qr_payload("mush-00042"), "MUSH-00042")

    def test_rejects_untrusted_or_malformed_payload(self):
        self.assertIsNone(parse_unit_qr_payload("http://example.com"))
        self.assertIsNone(parse_unit_qr_payload("MUSHROOMGUARD:UNKNOWN-0001"))
        self.assertIsNone(parse_unit_qr_payload("MUSHROOMGUARD:MICRO-1"))

    def test_stage_labels(self):
        self.assertEqual(stage_name("microgreen", 2), "Germination")
        self.assertEqual(stage_name("mushroom", 3), "Pinhead Formation & Fruiting")
        self.assertEqual(stage_name("microgreen", 9), "Unknown stage")

    def test_decodes_project_generated_qr(self):
        import qrcode
        from PIL import Image
        image = qrcode.make("MUSHROOMGUARD:MUSH-00001").convert("RGB")
        output = BytesIO()
        image.save(output, format="JPEG")
        raw = decode_unit_qr_from_jpeg(output.getvalue())
        self.assertEqual(parse_unit_qr_payload(raw), "MUSH-00001")


if __name__ == "__main__":
    unittest.main()
