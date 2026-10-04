"""Read-only DRB inspection: MediaPoolItem has no public Fusion composition API.

Accept explicit Text+ and custom Fusion title metadata. User-assigned clip names
are never used as a type guess (adjustment clips can be renamed arbitrarily).
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
import sqlite3
import os

MAX_XML = 64 * 1024 * 1024
MAX_COMP = 8 * 1024 * 1024

def generator_fields(blob):
    """Read top-level protobuf scalar strings; don't classify from user names."""
    data = blob
    if len(blob) > 9 and blob[:4] == b"\0\0\0\2":
        if blob[8] == 0x80:
            data = blob[9:]
        elif blob[8] == 0x81:
            if int.from_bytes(blob[4:8], "big") > MAX_COMP:
                return {}
            try:
                try:
                    from compression.zstd import ZstdDecompressor
                except ImportError:
                    from backports.zstd import ZstdDecompressor
                worker = ZstdDecompressor()
                data = worker.decompress(blob[9:], max_length=MAX_COMP + 1)
                if not worker.eof or len(data) > MAX_COMP:
                    return {}
            except Exception:
                return {}
    fields, position = {}, 0
    def varint():
        nonlocal position
        value, shift = 0, 0
        while position < len(data) and shift < 64:
            byte = data[position]
            position += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
            shift += 7
        raise ValueError("invalid protobuf")
    try:
        while position < len(data):
            key = varint()
            wire, field = key & 7, key >> 3
            if not field:
                break
            if wire == 2:
                length = varint()
                if position + length > len(data):
                    break
                fields[field] = data[position:position+length]
                position += length
            elif wire == 0:
                varint()
            elif wire in (1, 5):
                position += 8 if wire == 1 else 4
            else:
                break
    except ValueError:
        pass
    return fields

def bounded_inflate(raw):
    if len(raw) < 6:
        return b""
    expected = int.from_bytes(raw[:4], "big")
    if expected > MAX_COMP:
        return b""
    try:
        worker = zlib.decompressobj()
        result = worker.decompress(raw[4:], MAX_COMP + 1)
        return result if worker.eof and len(result) <= MAX_COMP else b""
    except zlib.error:
        return b""

def inspect_catalog(path):
    """Return accepted IDs/names and counts; never extract ZIP paths to disk."""
    ids, covered_ids, by_name, covered_names, rejected, total = set(), set(), {}, {}, 0, 0
    paths = path if isinstance(path, (tuple, list)) else [path]
    for file in paths:
      with zipfile.ZipFile(Path(file)) as archive:
        files = [entry for entry in archive.infolist() if entry.filename.endswith("/MpFolder.xml")]
        if len(files) > 1024 or sum(x.file_size for x in files) > MAX_XML:
            raise ValueError("Catálogo de estilos supera el límite de lectura")
        for entry in files:
            xml = archive.read(entry)
            if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise ValueError("Metadatos de plantilla no válidos")
            folder = ET.fromstring(xml)
            for item in folder.findall("./MediaVec/Element/*"):
                name, uid = item.findtext("Name") or "", item.findtext("UniqueMediaPoolItemId") or ""
                if not item.tag.startswith("Sm2MpGenerator"):
                    continue
                total += 1
                fields = {}
                try:
                    metadata = bytes.fromhex(item.findtext("FieldsBlob") or "")
                    fields = generator_fields(metadata)
                    source_ids = [fields[x] for x in (6, 7) if x in fields]
                    # Resolve stores the source generator's ID in protobuf fields
                    # 6 and 7. This survives user renaming of a title or adjustment.
                    explicit = any(value in (b"Text+", b"TextPlus") for value in source_ids)
                    typed_data = b" ".join(source_ids + [fields.get(2, b"")]) if fields else metadata
                    is_adjustment = any(x in typed_data.lower() for x in
                                        (b"adjustment", b"adjust clip", b"adjustclip"))
                    composition_text = []
                    for composition in item.findall(".//CompositionBA"):
                        raw = bytes.fromhex(composition.text or "")
                        composition_text.append(bounded_inflate(raw))
                    has_text = explicit or any(
                        re.search(rb'TEMPLATE_ID\s*=\s*"Text\+"', text) or
                        re.search(rb'\b[A-Za-z_][\w]*\s*=\s*TextPlus\s*\{', text)
                        for text in composition_text)
                    # Custom Fusion titles may have opaque/compressed tool data.
                    # Keep an explicit Fusion Title classification unless the
                    # metadata positively identifies it as an adjustment clip.
                    declared_title = b"Fusion Title" in typed_data
                    accepted = bool((has_text or declared_title) and not is_adjustment)
                except (ValueError, TypeError):
                    accepted = False
                if accepted:
                    ids.update(value for value in (uid, item.get("DbId"), item.findtext("MediaId")) if value)
                # A populated export can contain unrelated adjustment clips
                # while omitting the active project's titles. Count exact IDs,
                # including rejected generators, rather than trusting its size.
                known = bool(accepted or (fields and any(fields.get(x) for x in (2,6,7))))
                if known:
                    covered_ids.update(value for value in (uid,item.get("DbId"),item.findtext("MediaId")) if value)
                covered_names.setdefault(name, []).append((known,accepted))
                by_name.setdefault(name, []).append(accepted)
                if not accepted:
                    rejected += 1
    # For legacy Resolve versions without public item IDs, an ambiguous name is
    # rejected rather than admitting a same-named adjustment clip.
    names = {name for name, matches in by_name.items() if matches and all(matches)}
    classified_names = {name for name,matches in covered_names.items()
        if matches and all(known for known,_ in matches) and len({accepted for _,accepted in matches}) == 1}
    return {"ids": ids, "names": names, "coveredIds":covered_ids,"coveredNames":classified_names,
            "generators": total, "rejected": rejected}

def catalog_missing(items, catalog):
    """Unknown IDs are missing metadata, never proof that a title was removed."""
    covered = catalog.get("coveredIds", catalog["ids"])
    names = catalog.get("coveredNames", catalog["names"])
    return [item for item in items if (item.get("mediaId") not in covered if item.get("mediaId")
                                     else item.get("value") not in names)]

def filter_templates(items, catalog):
    return [{"label": x["label"], "value": x["value"]} for x in items
            if (x.get("mediaId") in catalog["ids"] if x.get("mediaId") else
                x.get("value") in catalog["names"])]


def library_roots():
    """Discover local DISK libraries; never connect to network project servers."""
    support = Path(os.environ.get("APPDATA", "")) / "Blackmagic Design/DaVinci Resolve"
    roots = [support / "Support/Resolve Project Library"]
    try:
        for line in (support / "Preferences/dblist.conf").read_text(encoding="utf-8-sig").splitlines():
            parts = line.split(":")
            if len(parts) < 3 or parts[-1] != "DISK":
                continue
            value = parts[1]
            if len(value) > 2 and value[0].isalpha() and value[1] in "\\/":
                value = value[0] + ":" + value[1:]
            path = Path(value)
            if path.is_absolute():
                roots.append(path)
    except (OSError, UnicodeError):
        pass
    return list(dict.fromkeys(roots))


def inspect_project_database(path, project_key, items):
    """Read a local library in read-only mode and match exact API item IDs.

    Resolve 20 may export generator bins with empty MediaVec entries. Its local
    SQLite metadata retains the source generator even when clips are renamed.
    No SQL mutations, schema changes, timeline operations or name-based matching.
    """
    ids, covered_ids, rejected, matched = set(), set(), 0, 0
    wanted = list(dict.fromkeys(x.get("mediaId") for x in items if x.get("mediaId")))
    connection = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=.25)
    try:
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute("SELECT SM_Project_id FROM SM_Project LIMIT 1").fetchone()
        if not row or row[0] != project_key:
            return None
        for offset in range(0, len(wanted), 100):
            batch = wanted[offset:offset+100]
            placeholders = ",".join("?" for _ in batch)
            query = ("SELECT Sm2MpMedia_id, UniqueMediaPoolItemId, DbType, FieldsBlob FROM Sm2MpMedia "
                     f"WHERE Sm2MpMedia_id IN ({placeholders}) OR UniqueMediaPoolItemId IN ({placeholders})")
            for uid, unique_id, kind, blob in connection.execute(query, batch + batch):
                matched += 1
                fields = generator_fields(blob or b"")
                source = b" ".join(fields.get(x, b"") for x in (2, 6, 7))
                adjustment = any(x in source.lower() for x in (b"adjustment", b"adjust clip", b"adjustclip"))
                title = any(fields.get(x) in (b"Text+", b"TextPlus") for x in (6, 7)) or fields.get(2) == b"Fusion Title"
                accepted = kind.startswith("Sm2MpGenerator") and title and not adjustment
                if not kind.startswith("Sm2MpGenerator") or source.strip():
                    covered_ids.update(x for x in (uid,unique_id) if x)
                if accepted:
                    ids.update(x for x in (uid, unique_id) if x)
                else:
                    rejected += 1
        return {"ids": ids, "names": set(), "coveredIds":covered_ids,"coveredNames":set(),
                "generators": matched, "rejected": rejected,
                "source": "local-library-read-only"}
    finally:
        connection.close()


def inspect_local_library(project_key, project_name, items, roots=None):
    for root in library_roots() if roots is None else roots:
        directory = Path(root) / "Resolve Projects/Users/guest/Projects"
        visited = 0
        for current, children, files in os.walk(directory):
            visited += 1
            if visited > 5000:
                break
            children[:] = [x for x in children if x not in ("Batch Renders", "CacheClip", "ProjectMetadataCache")]
            if "Project.db" not in files or Path(current).name != project_name:
                continue
            result = inspect_project_database(Path(current) / "Project.db", project_key, items)
            if result is not None:
                return result
    raise ValueError("No se encontró la biblioteca local del proyecto por su ID")
