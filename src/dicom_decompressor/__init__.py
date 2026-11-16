import argparse
import logging
import re
from pathlib import Path

import gdcm

log = logging.getLogger("dicom-decompressor")

# Explicit VR keeps each element's value representation in the file,
# which matters for private tags; Implicit VR would drop it.
TARGET_SYNTAX = gdcm.TransferSyntax.ExplicitVRLittleEndian

DIRECTORY_RECORD_SEQUENCE = gdcm.Tag(0x0004, 0x1220)
REFERENCED_FILE_ID = gdcm.Tag(0x0004, 0x1500)
SERIES_INSTANCE_UID = gdcm.Tag(0x0020, 0x000E)
SERIES_NUMBER = gdcm.Tag(0x0020, 0x0011)
SERIES_DESCRIPTION = gdcm.Tag(0x0008, 0x103E)
INSTANCE_NUMBER = gdcm.Tag(0x0020, 0x0013)


def get_string(ds: gdcm.DataSet, tag: gdcm.Tag) -> str:
    """Return a tag's value as a stripped string, or '' if absent/empty."""
    if not ds.FindDataElement(tag):
        return ""
    bv = ds.GetDataElement(tag).GetByteValue()
    if bv is None:
        return ""
    return str(bv).strip(" \x00")


def referenced_files(dicomdir: Path) -> list[Path]:
    """List all files referenced by the directory records of a DICOMDIR."""
    reader = gdcm.Reader()
    reader.SetFileName(str(dicomdir))
    if not reader.Read():
        raise RuntimeError(f"could not read {dicomdir}")

    ds = reader.GetFile().GetDataSet()
    if not ds.FindDataElement(DIRECTORY_RECORD_SEQUENCE):
        raise RuntimeError(f"{dicomdir} has no directory records; is it a DICOMDIR?")

    sq = ds.GetDataElement(DIRECTORY_RECORD_SEQUENCE).GetValueAsSQ()
    files = []
    for i in range(1, sq.GetNumberOfItems() + 1):  # gdcm items are 1-based
        record = sq.GetItem(i).GetNestedDataSet()
        file_id = get_string(record, REFERENCED_FILE_ID)
        if file_id:
            # Referenced File ID components are separated by backslashes.
            files.append(dicomdir.parent.joinpath(*file_id.split("\\")))
    return files


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")


def series_folder_name(ds: gdcm.DataSet) -> str:
    number = get_string(ds, SERIES_NUMBER)
    description = safe_name(get_string(ds, SERIES_DESCRIPTION))
    parts = []
    if number.isdigit():
        parts.append(f"S{int(number):03d}")
    if description:
        parts.append(description)
    return "_".join(parts) or safe_name(get_string(ds, SERIES_INSTANCE_UID)) or "unknown_series"


def unique_path(path: Path) -> Path:
    """Append _2, _3, ... to path until it does not exist."""
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        n += 1
    return candidate


def decompress_dicomdir(dicomdir: Path) -> Path:
    """Decompress every image referenced by a DICOMDIR into one folder per series.

    Output goes to '<folder containing DICOMDIR>_decompressed'. Files that cannot
    be decompressed are logged and skipped.
    """
    dicomdir = dicomdir.resolve()
    src_dir = dicomdir.parent
    out_dir = src_dir.with_name(f"{src_dir.name}_decompressed")
    out_dir.mkdir(exist_ok=True)

    series_dirs: dict[str, Path] = {}  # SeriesInstanceUID -> output folder
    ok = skipped = 0

    for src in referenced_files(dicomdir):
        reader = gdcm.ImageReader()
        reader.SetFileName(str(src))
        if not reader.Read():
            log.warning("Skipping %s: not a readable DICOM image", src)
            skipped += 1
            continue

        ds = reader.GetFile().GetDataSet()
        uid = get_string(ds, SERIES_INSTANCE_UID)
        if uid not in series_dirs:
            # Different series can share a number/description; keep them apart.
            series_dirs[uid] = unique_path(out_dir / series_folder_name(ds))
            series_dirs[uid].mkdir()
        series_dir = series_dirs[uid]

        instance = get_string(ds, INSTANCE_NUMBER)
        stem = f"{int(instance):05d}" if instance.isdigit() else src.stem
        dst = unique_path(series_dir / f"{stem}.dcm")

        change = gdcm.ImageChangeTransferSyntax()
        change.SetTransferSyntax(gdcm.TransferSyntax(TARGET_SYNTAX))
        change.SetInput(reader.GetImage())
        if not change.Change():
            log.warning("Skipping %s: could not change transfer syntax", src)
            skipped += 1
            continue

        writer = gdcm.ImageWriter()
        writer.SetFileName(str(dst))
        writer.SetFile(reader.GetFile())
        writer.SetImage(change.GetOutput())
        if not writer.Write():
            log.warning("Skipping %s: could not write %s", src, dst)
            dst.unlink(missing_ok=True)  # don't leave partial output behind
            skipped += 1
            continue

        log.info("Decompressed %s -> %s", src.relative_to(src_dir), dst.relative_to(out_dir))
        ok += 1

    log.info(
        "Done: %d decompressed into %d series, %d skipped -> %s",
        ok, len(series_dirs), skipped, out_dir,
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dicom-decompressor",
        description="Decompress all images referenced by a DICOMDIR, one folder per series.",
    )
    parser.add_argument("dicomdir", type=Path, help="path to the DICOMDIR file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.dicomdir.is_file():
        parser.error(f"not a file: {args.dicomdir}")

    try:
        decompress_dicomdir(args.dicomdir)
    except RuntimeError as e:
        parser.exit(1, f"error: {e}\n")
