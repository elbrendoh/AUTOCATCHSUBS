"""Verify signing boundaries without trusting a synthetic certificate or calling a service."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signing_artifact import OWN_FILES, compare, pe_payload, prepare


def executable(signed=False, pe32=False, overlay=b'PyInstaller payload'):
    data = bytearray(1024)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 128)
    data[128:132] = b'PE\0\0'
    optional_size = 224 if pe32 else 240
    struct.pack_into('<H', data, 134, 1)
    struct.pack_into('<H', data, 148, optional_size)
    optional = 152
    struct.pack_into('<H', data, optional, 0x10b if pe32 else 0x20b)
    directories = 96 if pe32 else 112
    struct.pack_into('<I', data, optional + directories - 4, 16)
    struct.pack_into('<II', data, optional + optional_size + 16, 512, 512)
    data[512:1024] = b'X' * 512
    data.extend(overlay)
    if signed:
        data.extend(b'\0' * ((-len(data)) % 8))
        struct.pack_into('<II', data, optional + directories + 32, len(data), 16)
        struct.pack_into('<I', data, optional + 64, 12345)
        data.extend(struct.pack('<IHH', 16, 0x200, 2) + b'CERTFAKE')
    return bytes(data)


class SigningArtifactTests(unittest.TestCase):
    def test_certificate_and_checksum_do_not_change_payload_digest(self):
        for pe32 in (False, True):
            with self.subTest(pe32=pe32):
                original, original_signed = pe_payload(executable(pe32=pe32))
                returned, returned_signed = pe_payload(executable(signed=True, pe32=pe32))
                self.assertEqual(original, returned)
                self.assertFalse(original_signed)
                self.assertTrue(returned_signed)

    def test_code_and_backend_overlay_changes_are_detected(self):
        original = pe_payload(executable())[0]
        changed_code = bytearray(executable(signed=True))
        changed_code[600] ^= 1
        self.assertNotEqual(original, pe_payload(changed_code)[0])
        self.assertNotEqual(original, pe_payload(executable(signed=True, overlay=b'Another payload'))[0])

    def test_malformed_certificate_and_trailing_overlay_are_rejected(self):
        for data in (b'not a PE', executable(signed=True) + b'extra'):
            with self.assertRaises(ValueError):
                pe_payload(data)
        invalid = bytearray(executable(signed=True))
        struct.pack_into('<II', invalid, 152 + 112 + 32, 512, len(invalid) - 512)
        with self.assertRaises(ValueError):
            pe_payload(invalid)

    def test_stage_only_own_files_and_never_merge_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package, stage = root / 'package', root / 'stage'
            package.mkdir()
            for name in OWN_FILES:
                (package / name).write_bytes(executable())
            (package / 'ffmpeg.exe').write_bytes(b'third party')
            (package / 'codes-private.txt').write_text('DO NOT COPY')
            result = prepare(package, stage)
            self.assertEqual(set(result), set(OWN_FILES))
            self.assertEqual({file.name for file in stage.iterdir()}, set(OWN_FILES))
            with self.assertRaises(ValueError):
                prepare(package, stage)

    def test_returned_artifact_requires_signatures_same_payload_and_exact_file_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original, returned = root / 'original', root / 'returned'
            original.mkdir()
            returned.mkdir()
            for name in OWN_FILES:
                (original / name).write_bytes(executable())
                (returned / name).write_bytes(executable(signed=True))
            self.assertEqual(set(compare(original, returned)), set(OWN_FILES))
            (returned / OWN_FILES[0]).write_bytes(executable())
            with self.assertRaises(ValueError):
                compare(original, returned)
            (returned / OWN_FILES[0]).write_bytes(executable(signed=True, overlay=b'changed'))
            with self.assertRaises(ValueError):
                compare(original, returned)
            (returned / OWN_FILES[0]).write_bytes(executable(signed=True))
            (returned / 'unrelated.dll').write_bytes(b'unexpected')
            with self.assertRaises(ValueError):
                compare(original, returned)

    def test_project_xml_has_no_upstream_wildcard_or_signing_target(self):
        root = Path(__file__).resolve().parents[2]
        ns = {'s': 'http://signpath.io/artifact-configuration/v1'}
        config = ET.parse(root / '.signpath/artifact-configurations/jr-binaries.xml').getroot()
        elements = config.findall('s:zip-file/s:pe-file', ns)
        self.assertEqual({element.attrib['path'] for element in elements}, set(OWN_FILES))
        self.assertEqual(len(elements), 2)
        for element in elements:
            self.assertEqual(element.attrib['product-name'], 'AUTOCATCHSUBS JR')
            self.assertEqual(element.attrib['product-version'], '${version}')
            self.assertIsNotNone(element.find('s:authenticode-sign', ns))


if __name__ == '__main__':
    unittest.main()
