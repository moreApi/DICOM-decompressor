import argparse
import logging
import sys
from pathlib import Path

import gdcm

log = logging.getLogger("dicom-decompressor")

# Explicit VR keeps each element's value representation in the file,
# which matters for private tags; Implicit VR would drop it.
TARGET_SYNTAX = gdcm.TransferSyntax.ExplicitVRLittleEndian


def decompress_file(src: Path, dst: Path) -> None:
    """Decompress one DICOM file. Raises RuntimeError on failure."""
    reader = gdcm.ImageReader()
    reader.SetFileName(str(src))
    if not reader.Read():
        raise RuntimeError("not a readable DICOM image")

    change = gdcm.ImageChangeTransferSyntax()
    change.SetTransferSyntax(gdcm.TransferSyntax(TARGET_SYNTAX))
    change.SetInput(reader.GetImage())
    if not change.Change():
        raise RuntimeError("could not change transfer syntax")

    writer = gdcm.ImageWriter()
    writer.SetFileName(str(dst))
    writer.SetFile(reader.GetFile())
    writer.SetImage(change.GetOutput())
    if not writer.Write():
        raise RuntimeError("could not write output file")


def decompress_folder(src_dir: Path) -> Path:
    """Decompress every file under src_dir into a sibling '<name>_decompressed' folder.

    Subfolders are mirrored. Files that cannot be decompressed are logged and skipped.
    """
    src_dir = src_dir.resolve()
    dst_dir = src_dir.with_name(f"{src_dir.name}_decompressed")
    dst_dir.mkdir(exist_ok=True)

    ok = skipped = 0
    for src in sorted(p for p in src_dir.rglob("*") if p.is_file()):
        dst = dst_dir / src.relative_to(src_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            decompress_file(src, dst)
        except RuntimeError as e:
            log.warning("Skipping %s: %s", src, e)
            dst.unlink(missing_ok=True)  # don't leave partial output behind
            skipped += 1
        else:
            log.info("Decompressed %s", src.relative_to(src_dir))
            ok += 1

    log.info("Done: %d decompressed, %d skipped -> %s", ok, skipped, dst_dir)
    return dst_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dicom-decompressor",
        description="Decompress all DICOM files in a folder into '<folder>_decompressed'.",
    )
    parser.add_argument("folder", type=Path, help="folder containing DICOM files")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not args.folder.is_dir():
        parser.error(f"not a folder: {args.folder}")

    decompress_folder(args.folder)
    sys.exit(0)
