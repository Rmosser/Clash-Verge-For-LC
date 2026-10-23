#!/usr/bin/env python3
"""Pack registry-original Node OCI blobs, avoiding truncated lzc-cli local layers."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile


def repack(package: Path, archive: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="clash-oci-") as temporary:
        root = Path(temporary)
        source, target = root / "source", root / "package"
        source.mkdir()
        target.mkdir()
        for path, destination in ((archive, source), (package, target)):
            if path.is_dir():
                shutil.copytree(path, destination, dirs_exist_ok=True)
            else:
                with tarfile.open(path) as handle:
                    handle.extractall(destination, filter="data")
        index = json.loads((source / "index.json").read_text())
        assert len(index["manifests"]) == 1, "expected one platform manifest"
        descriptor = index["manifests"][0]

        def blob(item):
            digest = item["digest"]
            assert digest.startswith("sha256:") and len(digest) == 71
            path = source / "blobs" / "sha256" / digest[7:]
            data = path.read_bytes()
            assert len(data) == item["size"], "OCI blob size mismatch"
            assert hashlib.sha256(data).hexdigest() == digest[7:], "OCI blob digest mismatch"
            return data

        manifest = json.loads(blob(descriptor))
        config = json.loads(blob(manifest["config"]))
        assert config["architecture"] == "amd64" and config["os"] == "linux"
        diff_ids = config["rootfs"]["diff_ids"]
        assert len(diff_ids) == len(manifest["layers"])
        for layer, diff_id in zip(manifest["layers"], diff_ids):
            data = blob(layer)
            raw = gzip.decompress(data) if "gzip" in layer["mediaType"] else data
            assert "sha256:" + hashlib.sha256(raw).hexdigest() == diff_id
            with tarfile.open(fileobj=io.BytesIO(raw)) as handle:
                # Read every regular file; listing alone can miss truncated bodies.
                for entry in handle:
                    if entry.isfile():
                        stream = handle.extractfile(entry)
                        while stream.read(1024 * 1024):
                            pass
        descriptor["annotations"] = {"org.opencontainers.image.ref.name": "fetchproxy-runtime"}
        (source / "index.json").write_text(json.dumps(index))
        shutil.rmtree(target / "images")
        shutil.copytree(source, target / "images")
        (target / "images.lock").write_text(json.dumps({"version": 1, "images": {
            "fetchproxy-runtime": {"image_id": manifest["config"]["digest"], "upstream": "", "layers": [
                {"digest": layer["digest"], "source": "embed"} for layer in manifest["layers"]
            ]}
        }}))
        output = package.with_suffix(".repack.tmp")
        try:
            with tarfile.open(output, "w") as handle:
                for child in sorted(target.iterdir()):
                    handle.add(child, arcname=child.name)
            os.replace(output, package)
        finally:
            output.unlink(missing_ok=True)
        print("Verified and packed original Node OCI layers (linux/amd64).")


if __name__ == "__main__":
    repack(Path(sys.argv[1]), Path(sys.argv[2]))
