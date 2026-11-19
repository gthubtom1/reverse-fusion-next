"""Rebuild the Windows x64 inventory reader from the included source snapshot."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
SOURCE = "478d1fba2410f78af77d3f6678e476a9c9adab5ea2e8450b049a71f9a5ed0091"
COMPILER = "go version go1.27.1 windows/amd64"


def main():
    archive = HERE/"parser-source.zip"
    if sha256(archive.read_bytes()).hexdigest() != SOURCE:
        raise ValueError("Parser source digest differs")
    env = os.environ | {"GOPROXY":"off", "GOWORK":"off", "GOTOOLCHAIN":"local", "CGO_ENABLED":"0",
                        "GOOS":"windows", "GOARCH":"amd64", "GOAMD64":"v1","GOFLAGS":""}
    if subprocess.check_output(["go","version"],text=True,env=env).strip() != COMPILER:
        raise ValueError("Required compiler: " + COMPILER)
    with tempfile.TemporaryDirectory(prefix="rf-inventory-build-") as temp:
        root = Path(temp)
        with zipfile.ZipFile(archive) as package:
            package.extractall(root)
        shutil.copyfile(HERE/"main.go",root/"inventory.go")
        subprocess.run(["go","build","-buildvcs=false","-trimpath","-ldflags","-s -w -buildid=",
                        "-o","inventory.exe","inventory.go"],cwd=root,env=env,check=True)
        raw = (root/"inventory.exe").read_bytes()
        if raw != (HERE/"inventory.exe").read_bytes():
            raise ValueError("Rebuilt executable differs")
    print(json.dumps({"parser_source_sha256":SOURCE, "reader_sha256":sha256(raw).hexdigest(),
                      "compiler":COMPILER,"network_dependencies":False}))


if __name__ == "__main__":
    main()
