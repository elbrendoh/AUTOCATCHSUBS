"""Stage only our two JR binaries; verify returned PE content before accepting signatures.

This does NOT validate certificate trust (verify-signpath.ps1 does that). The
payload comparison is deliberately separate from the Windows signature check.
No package, installer, license state or installed application is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

OWN_FILES = ('AUTOCATCHSUBS.exe', 'AUTOCATCHSUBSBackend.exe')


def pe_payload(data):
    """Hash PE bytes including overlays, except Authenticode fields/certificate.

Normalise the checksum, security directory, and up to seven bytes of alignment
padding before the certificate. Reject certificate tables inside the image,
trailing content after the table, and malformed headers. This is a content
equivalence check, not an implementation of Authenticode trust verification.
"""
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('Not a PE file')
    pe = struct.unpack_from('<I', data, 60)[0]
    if pe < 64 or pe + 24 > len(data) or data[pe:pe+4] != b'PE\0\0':
        raise ValueError('Invalid PE header')
    count, optional_size = struct.unpack_from('<H', data, pe+6)[0], struct.unpack_from('<H', data, pe+20)[0]
    optional = pe + 24
    end_headers = optional + optional_size + count * 40
    if optional_size < 2 or end_headers > len(data):
        raise ValueError('Truncated PE headers')
    magic = struct.unpack_from('<H', data, optional)[0]
    directories = {0x10b: 96, 0x20b: 112}.get(magic)
    if directories is None or optional_size < directories + 40:
        raise ValueError('Unsupported PE optional header')
    number = struct.unpack_from('<I', data, optional + directories - 4)[0]
    if number < 5:
        raise ValueError('Missing PE security directory')
    checksum = optional + 64
    security = optional + directories + 32
    offset, size = struct.unpack_from('<II', data, security)
    image_end = end_headers
    for index in range(count):
        section = optional + optional_size + index * 40
        raw_size, raw_offset = struct.unpack_from('<II', data, section + 16)
        if raw_size and (raw_offset < end_headers or raw_offset + raw_size > len(data)):
            raise ValueError('Invalid PE section extent')
        image_end = max(image_end, raw_offset + raw_size)
    if bool(offset) != bool(size):
        raise ValueError('Incomplete certificate directory')
    if size:
        if offset % 8 or offset < image_end or offset + size != len(data) or size < 8:
            raise ValueError('Invalid certificate table extent')
        cursor = offset
        while cursor < offset + size:
            if cursor + 8 > offset + size:
                raise ValueError('Truncated certificate entry')
            length = struct.unpack_from('<I', data, cursor)[0]
            if length < 8 or cursor + length > offset + size:
                raise ValueError('Invalid certificate entry')
            cursor += (length + 7) & ~7
        if cursor != offset + size:
            raise ValueError('Misaligned certificate table')
    body = bytearray(data[:offset] if size else data)
    body[checksum:checksum+4] = b'\0' * 4
    body[security:security+8] = b'\0' * 8
    body.extend(b'\0' * ((-len(body)) % 8))
    return hashlib.sha256(body).hexdigest(), bool(size)


def exact_files(directory):
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('Artifact must be a real directory')
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != set(OWN_FILES):
        raise ValueError('Artifact must contain exactly the two project executables')
    if any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise ValueError('Links and nested entries are not signing inputs')


def prepare(package, output):
    package, output = Path(package), Path(output)
    if output.exists():
        raise ValueError('Signing stage already exists; refusing to merge files')
    records = {}
    for name in OWN_FILES:
        source = package / name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Missing real project executable: ' + name)
        data = source.read_bytes()
        payload, signed = pe_payload(data)
        if signed:
            raise ValueError('Expected fresh unsigned project executable: ' + name)
        records[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'payload_sha256': payload}
    output.mkdir(parents=True)
    for name in OWN_FILES:
        shutil.copy2(package / name, output / name)
    exact_files(output)
    return records


def compare(original, returned):
    exact_files(original)
    exact_files(returned)
    records = {}
    for name in OWN_FILES:
        before = (Path(original) / name).read_bytes()
        after = (Path(returned) / name).read_bytes()
        payload_before, signed_before = pe_payload(before)
        payload_after, signed_after = pe_payload(after)
        if signed_before or not signed_after or payload_before != payload_after:
            raise ValueError('Returned executable content/signing state differs: ' + name)
        records[name] = {'sha256': hashlib.sha256(after).hexdigest(), 'payload_sha256': payload_after}
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'compare'))
    parser.add_argument('original', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.resolve().parent == args.output.resolve():
        parser.error('Reports must stay outside the signing artifact')
    records = prepare(args.original, args.output) if args.operation == 'prepare' else compare(args.original, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({'operation': args.operation, 'files': records,
                                      'certificate_trust_verified': False}, indent=2), encoding='utf-8')
    print('Project-only signing artifact ' + args.operation + ' passed; certificate trust is checked separately.')


if __name__ == '__main__':
    main()
