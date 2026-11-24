"""struct 모듈 바이너리 레이아웃, 패딩, 바이트 순서, 검증 헤더 설계를 비교한다.

실행: python3 src/struct_binary_layout.py
"""

from __future__ import annotations

import re
import struct
import sys
import timeit
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 1. 레코드 형식 비교: 네이티브(@), 표준(=), 리틀엔디언(<)
# ---------------------------------------------------------------------------

SENSOR_RECORD_NATIVE = "@bid"
SENSOR_RECORD_STANDARD = "=bid"
SENSOR_RECORD_LITTLE = "<bid"


@dataclass
class SensorData:
    """센서 레코드: kind(int8), count(int32), ratio(float64)"""

    kind: int
    count: int
    ratio: float


def compare_format_sizes() -> dict[str, int]:
    """같은 레코드를 세 형식으로 패킹했을 때 크기를 반환한다."""
    return {
        "native(@)": struct.calcsize(SENSOR_RECORD_NATIVE),
        "standard(=)": struct.calcsize(SENSOR_RECORD_STANDARD),
        "little(<)": struct.calcsize(SENSOR_RECORD_LITTLE),
    }


def encode_sensor(data: SensorData, fmt: str) -> bytes:
    """SensorData를 지정 형식으로 패킹한다."""
    return struct.pack(fmt, data.kind, data.count, data.ratio)


def decode_sensor(payload: bytes, fmt: str) -> SensorData:
    """지정 형식으로 패킹된 바이트를 SensorData로 복원한다."""
    kind, count, ratio = struct.unpack(fmt, payload)
    return SensorData(kind, count, ratio)


# ---------------------------------------------------------------------------
# 2. 패딩 분석
# ---------------------------------------------------------------------------


def padding_report(fmt: str) -> list[tuple[str, int, int, int]]:
    """형식 문자열의 각 필드 오프셋과 패딩을 계산한다.

    반환: (필드문자, 필드크기, 오프셋, 패딩) 리스트
    필드문자는 반복 카운트 포함(예: "3h"). 패딩은 필드 뒤에 추가된 바이트 수.
    총 오프셋+필드크기+패딩의 합은 calcsize(fmt)와 일치해야 한다.

    지원: 단일 필드, 반복(3h), x(패딩), 0i 같은 정렬. s는 간단한 경우만.
    복잡한 중첩/조건부 형식은 지원하지 않는다.
    """
    if not fmt:
        return []
    byteorder = fmt[0] if fmt[0] in "@=<>!" else "@"
    fields_part = fmt[1:] if fmt[0] in "@=<>!" else fmt
    total_size = struct.calcsize(fmt)
    field_pattern = re.compile(r"(\d*)([xcbB?hHiIlLqQnNefd]|(\d+)[sp])")
    result: list[tuple[str, int, int, int]] = []
    pos = 0
    while pos < len(fields_part):
        match = field_pattern.match(fields_part, pos)
        if not match:
            raise ValueError(f"지원하지 않는 형식 문자: {fields_part[pos:pos+10]}")
        full = match.group(0)
        count_str = match.group(1)
        typecode = match.group(2)
        s_count = match.group(3)
        count = int(count_str) if count_str else 1
        if s_count:
            count = int(s_count)
        if typecode == "x":
            field_size = count
        else:
            single_fmt = byteorder + typecode
            field_size = struct.calcsize(single_fmt) * count
        prefix = byteorder + fields_part[: pos + len(full)]
        current_end = struct.calcsize(prefix)
        offset = current_end - field_size
        if pos + len(full) < len(fields_part):
            next_char_pos = pos + len(full)
            next_match = field_pattern.match(fields_part, next_char_pos)
            if next_match:
                next_prefix = byteorder + fields_part[: next_char_pos + len(next_match.group(0))]
                next_end = struct.calcsize(next_prefix)
                next_field_start = next_end
                if next_match.group(2) != "x":
                    next_single = byteorder + next_match.group(2)
                    next_field_size = struct.calcsize(next_single)
                    if next_match.group(1):
                        next_field_size *= int(next_match.group(1))
                    elif next_match.group(3):
                        next_field_size = int(next_match.group(3))
                    next_field_start = next_end - next_field_size
                else:
                    next_field_start = next_end - (int(next_match.group(1)) if next_match.group(1) else 1)
                padding = next_field_start - current_end
            else:
                padding = total_size - current_end
        else:
            padding = total_size - current_end
        result.append((full, field_size, offset, padding))
        pos += len(full)
    return result


# ---------------------------------------------------------------------------
# 3. 바이트 순서 혼동 시연
# ---------------------------------------------------------------------------


def demonstrate_byteorder_confusion(value: int) -> dict[str, Any]:
    """같은 바이트를 다른 바이트 순서로 읽었을 때 값이 바뀌는 것을 보여준다."""
    little = struct.pack("<I", value)
    big = struct.pack(">I", value)
    return {
        "original": value,
        "little_bytes": little.hex(),
        "big_bytes": big.hex(),
        "little_as_big": struct.unpack(">I", little)[0],
        "big_as_little": struct.unpack("<I", big)[0],
    }


# ---------------------------------------------------------------------------
# 4. 검증 헤더 설계
# ---------------------------------------------------------------------------

FRAME_HEADER_FMT = "<4sBBH"
FRAME_HEADER_STRUCT = struct.Struct(FRAME_HEADER_FMT)
FRAME_MAGIC = b"FRME"
FRAME_VERSION_1 = 1
FRAME_MAX_PAYLOAD = 65535


class FrameError(ValueError):
    """프레임 검증 실패 시 발생하는 예외."""


def encode_frame(payload: bytes, version: int = FRAME_VERSION_1, flags: int = 0) -> bytes:
    """고정 헤더 + payload 프레임을 만든다.

    Args:
        payload: 프레임에 담을 데이터
        version: 프레임 버전 (1~255)
        flags: 플래그 비트 (0~255)

    Raises:
        FrameError: payload 길이가 범위를 벗어나거나 버전/플래그가 범위 밖일 때
    """
    if not (1 <= version <= 255):
        raise FrameError(f"version은 1~255 범위여야 한다: {version}")
    if not (0 <= flags <= 255):
        raise FrameError(f"flags는 0~255 범위여야 한다: {flags}")
    payload_length = len(payload)
    if payload_length > FRAME_MAX_PAYLOAD:
        raise FrameError(
            f"payload 길이가 최대값을 초과한다: {payload_length} > {FRAME_MAX_PAYLOAD}"
        )
    header = FRAME_HEADER_STRUCT.pack(FRAME_MAGIC, version, flags, payload_length)
    return header + payload


def decode_frame(data: bytes) -> tuple[int, int, bytes]:
    """프레임을 파싱하고 (version, flags, payload)를 반환한다.

    Raises:
        FrameError: 헤더가 짧거나 magic 불일치, 알 수 없는 version, 길이 불일치
    """
    header_size = FRAME_HEADER_STRUCT.size
    if len(data) < header_size:
        raise FrameError(
            f"프레임이 헤더보다 짧다: {len(data)} < {header_size}"
        )
    try:
        magic, version, flags, payload_length = FRAME_HEADER_STRUCT.unpack(
            data[:header_size]
        )
    except struct.error as exc:
        raise FrameError(f"헤더 언팩 실패: {exc}") from exc
    if magic != FRAME_MAGIC:
        raise FrameError(f"magic 불일치: {magic!r} != {FRAME_MAGIC!r}")
    if version != FRAME_VERSION_1:
        raise FrameError(f"알 수 없는 version: {version}")
    expected_total = header_size + payload_length
    if len(data) < expected_total:
        raise FrameError(
            f"payload가 짧다: 선언={payload_length}, 실제={len(data) - header_size}"
        )
    if len(data) > expected_total:
        raise FrameError(
            f"payload가 길다: 선언={payload_length}, 실제={len(data) - header_size}"
        )
    payload = data[header_size : header_size + payload_length]
    return version, flags, payload


# ---------------------------------------------------------------------------
# 5. 레코드 배열 읽기
# ---------------------------------------------------------------------------


def read_record_array(data: bytes, fmt: str) -> list[tuple[Any, ...]]:
    """iter_unpack으로 레코드 배열을 읽는다.

    Raises:
        ValueError: 나머지 바이트가 있을 때 (오프셋 정보 포함)
    """
    record_size = struct.calcsize(fmt)
    if len(data) % record_size != 0:
        offset = (len(data) // record_size) * record_size
        raise ValueError(
            f"데이터가 레코드 크기의 배수가 아니다: {len(data)} % {record_size} != 0 "
            f"(오프셋 {offset}에서 {len(data) - offset}바이트 남음)"
        )
    return list(struct.iter_unpack(fmt, data))


# ---------------------------------------------------------------------------
# 6. 성능 비교
# ---------------------------------------------------------------------------


def performance_comparison(fmt: str, values: tuple[Any, ...], n: int = 100_000) -> dict[str, float]:
    """struct.pack vs 미리 컴파일한 Struct.pack 성능을 비교한다.

    Returns:
        각 방법의 실행 시간(초). 절대값은 환경마다 다르므로 상대 비교용.
    """
    compiled = struct.Struct(fmt)
    pack_time = timeit.timeit(lambda: struct.pack(fmt, *values), number=n)
    struct_time = timeit.timeit(lambda: compiled.pack(*values), number=n)
    return {
        "struct.pack": pack_time,
        "Struct.pack": struct_time,
        "ratio": pack_time / struct_time if struct_time > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# 데모
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"Python {sys.version.split()[0]}, {sys.byteorder}-endian")

    print("\n[1] 형식별 레코드 크기")
    sizes = compare_format_sizes()
    for name, size in sizes.items():
        print(f"  {name:16s} {size:2d} 바이트")

    print("\n[2] 같은 데이터를 세 형식으로 패킹")
    data = SensorData(kind=1, count=1000, ratio=0.5)
    for name, fmt_str in [
        ("native(@)", SENSOR_RECORD_NATIVE),
        ("standard(=)", SENSOR_RECORD_STANDARD),
        ("little(<)", SENSOR_RECORD_LITTLE),
    ]:
        encoded = encode_sensor(data, fmt_str)
        print(f"  {name:16s} {len(encoded):2d}바이트  {encoded.hex()}")

    print("\n[3] 패딩 분석 (@bi)")
    for field, size, offset, padding in padding_report("@bi"):
        print(f"  필드={field:4s} 크기={size} 오프셋={offset} 패딩={padding}")
    total = sum(size + padding for _, size, _, padding in padding_report("@bi"))
    print(f"  합계={total} (calcsize={struct.calcsize('@bi')})")

    print("\n[4] 바이트 순서 혼동")
    confusion = demonstrate_byteorder_confusion(1)
    print(f"  원본 값: {confusion['original']}")
    print(f"  리틀엔디언 바이트: {confusion['little_bytes']}")
    print(f"  빅엔디언으로 읽으면: {confusion['little_as_big']}")

    print("\n[5] 검증 헤더")
    payload = b"Hello"
    frame = encode_frame(payload)
    print(f"  프레임 크기: {len(frame)} (헤더 {FRAME_HEADER_STRUCT.size} + payload {len(payload)})")
    version, flags, decoded_payload = decode_frame(frame)
    print(f"  복원: version={version}, flags={flags}, payload={decoded_payload!r}")
    print("  거절 사례:")
    for bad, reason in [
        (b"XXXX" + frame[4:], "magic 불일치"),
        (frame[:6], "헤더보다 짧음"),
        (frame[:-1], "payload 짧음"),
        (frame + b"X", "payload 김"),
    ]:
        try:
            decode_frame(bad)
            print(f"    {reason}: 거절 실패!")
        except FrameError as exc:
            print(f"    {reason}: OK")

    print("\n[6] 레코드 배열")
    records = [(1, 10), (2, 20), (3, 30)]
    packed = b"".join(struct.pack("<bH", k, v) for k, v in records)
    decoded = read_record_array(packed, "<bH")
    print(f"  {len(records)}개 레코드 ({len(packed)}바이트) -> {decoded}")
    try:
        read_record_array(packed + b"\x00", "<bH")
    except ValueError as exc:
        print(f"  나머지 1바이트 거절: {str(exc)[:60]}...")

    print("\n[7] 성능 비교 (<iHd>, 100000회)")
    perf = performance_comparison("<iHd", (100, 200, 0.5), n=100_000)
    print(f"  struct.pack: {perf['struct.pack']:.4f}초")
    print(f"  Struct.pack: {perf['Struct.pack']:.4f}초")
    print(f"  비율(pack/Struct): {perf['ratio']:.2f}")


if __name__ == "__main__":
    main()
