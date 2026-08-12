import io
import os
import struct

from webutils.bank.wav import (
    find_wav_txt, read_wav_info, read_wav_list, wav_duration,
    wav_duration_file, write_wav_header,
)


def test_write_wav_header_pcm16():
    buf = io.BytesIO()
    write_wav_header(buf, 44100, 16, 2, 1000)
    data = buf.getvalue()
    assert data[0:4] == b"RIFF" and data[8:12] == b"WAVE"
    assert data[12:16] == b"fmt "
    assert struct.unpack_from("<H", data, 20)[0] == 1       # PCM
    assert struct.unpack_from("<I", data, 24)[0] == 44100
    assert struct.unpack_from("<I", data, 42)[0] == 1000    # data size
    assert data[38:42] == b"data"
    assert struct.unpack_from("<I", data, 4)[0] == 1000 + 38


def test_write_wav_header_float32():
    buf = io.BytesIO()
    write_wav_header(buf, 48000, 32, 1, 800)
    assert struct.unpack_from("<H", buf.getvalue(), 20)[0] == 3  # IEEE float


def test_read_wav_info_roundtrip():
    buf = io.BytesIO()
    write_wav_header(buf, 22050, 16, 1, 88200)
    info = read_wav_info(buf.getvalue())
    assert info == (88200, 22050, 1, 16)


def test_read_wav_info_invalid():
    assert read_wav_info(b"") is None
    assert read_wav_info(b"RIFFxx") is None


def test_wav_duration():
    assert wav_duration(88200, 22050, 1, 16) == 2.0
    assert wav_duration(0, 0, 0, 0) == 0.0


def test_wav_duration_file(tmp_path):
    buf = io.BytesIO()
    write_wav_header(buf, 44100, 16, 2, 44100 * 4)  # 1s
    p = tmp_path / "a.wav"
    p.write_bytes(buf.getvalue())
    assert wav_duration_file(str(p)) == 1.0
    assert wav_duration_file(str(tmp_path / "missing.wav")) is None


def test_wav_lists(tmp_path):
    sub = tmp_path / "B[0]"
    sub.mkdir()
    (sub / "B[0].txt").write_text("a.wav\nb.wav\n", encoding="utf-8")
    (tmp_path / "B[1].txt").write_text("c.wav\n", encoding="utf-8")
    assert find_wav_txt(str(tmp_path), "B[0]") == str(sub / "B[0].txt")
    assert find_wav_txt(str(tmp_path), "B[1]") == str(tmp_path / "B[1].txt")
    assert read_wav_list(str(sub / "B[0].txt")) == ["a.wav", "b.wav"]
    assert find_wav_txt(str(tmp_path), "missing") is None
