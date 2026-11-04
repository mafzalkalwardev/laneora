import pathlib
import struct
import zlib
import marshal
import types
import dis
import io

data = pathlib.Path(r"_reference/Awwthat Pro v2.3.exe").read_bytes()
pstart = 333312
k = data.find(b"sappv2.3\x00")
pos, csize, _ = struct.unpack(">III", data[k - 13 : k - 1])
raw = zlib.decompress(data[pstart + pos : pstart + pos + csize])
code = marshal.loads(raw)

out = []


def walk(co, prefix=""):
    buf = io.StringIO()
    buf.write(f"\n===== {prefix}{co.co_name} @ {co.co_filename} =====\n")
    buf.write(f"args={co.co_varnames[: co.co_argcount]} locals={co.co_varnames}\n")
    buf.write(f"names={co.co_names}\n")
    buf.write("consts:\n")
    for i, c in enumerate(co.co_consts):
        if isinstance(c, types.CodeType):
            buf.write(f"  [{i}] <code {c.co_name}>\n")
        else:
            buf.write(f"  [{i}] {c!r}\n")
    buf.write("dis:\n")
    dis.dis(co, file=buf)
    out.append(buf.getvalue())
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            walk(c, prefix + co.co_name + ".")


walk(code)
pathlib.Path("recovery/appv2.3.dis.txt").write_text("".join(out), encoding="utf-8")
print("ok", sum(len(x) for x in out))

text = "".join(out)
for marker in [
    " login @",
    " showSelectScreen @",
    " browse @",
    " make_tab @",
    " initCookies @",
    " initLocalStorage @",
    " streamAgain @",
    " start @",
    " decrypt @",
]:
    idx = text.find(marker)
    print("FOUND", marker, idx)
