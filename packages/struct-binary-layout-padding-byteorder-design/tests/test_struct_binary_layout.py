"""struct 바이너리 레이아웃 패딩, 바이트 순서, 검증 헤더 설계를 검증한다."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from struct_binary_layout import (
    FRAME_HEADER_STRUCT,
    FRAME_MAGIC,
    FRAME_MAX_PAYLOAD,
    FRAME_VERSION_1,
    SENSOR_RECORD_LITTLE,
    SENSOR_RECORD_NATIVE,
    SENSOR_RECORD_STANDARD,
    FrameError,
    SensorData,
    compare_format_sizes,
    decode_frame,
    decode_sensor,
    demonstrate_byteorder_confusion,
    encode_frame,
    encode_sensor,
    padding_report,
    performance_comparison,
    read_record_array,
)


class StandardFormatSizeTest(unittest.TestCase):
    """표준 형식(<, =, >)의 절대 크기를 확인한다."""

    def test_little_endian_sizes(self):
        self.assertEqual(struct.calcsize("<bi"), 5)
        self.assertEqual(struct.calcsize("<bq"), 9)
        self.assertEqual(struct.calcsize("<?h"), 3)
        self.assertEqual(struct.calcsize("<H"), 2)
        self.assertEqual(struct.calcsize("<I"), 4)
        self.assertEqual(struct.calcsize("<iHd"), 14)

    def test_standard_sizes_match_little(self):
        self.assertEqual(struct.calcsize("=bi"), struct.calcsize("<bi"))
        self.assertEqual(struct.calcsize("=bq"), struct.calcsize("<bq"))

    def test_big_endian_sizes_match_little(self):
        self.assertEqual(struct.calcsize(">bi"), struct.calcsize("<bi"))
        self.assertEqual(struct.calcsize("!bi"), struct.calcsize("<bi"))


class NativeFormatRulesTest(unittest.TestCase):
    """네이티브 형식(@)이 플랫폼 정렬 규칙을 따르는지 확인한다."""

    def test_native_adds_padding_for_alignment(self):
        self.assertGreaterEqual(struct.calcsize("@bi"), struct.calcsize("<bi"))

    def test_native_int_is_aligned(self):
        self.assertEqual(struct.calcsize("@bi") % struct.calcsize("@i"), 0)

    def test_native_no_trailing_padding_for_smaller_last(self):
        self.assertEqual(struct.calcsize("@ib"), struct.calcsize("@i") + 1)

    def test_native_trailing_padding_with_zero_field(self):
        self.assertEqual(struct.calcsize("@ib0i") % struct.calcsize("@i"), 0)
        self.assertGreater(struct.calcsize("@ib0i"), struct.calcsize("@ib"))

    def test_native_long_long_aligned(self):
        self.assertGreaterEqual(struct.calcsize("@bq"), struct.calcsize("<bq"))
        self.assertEqual(struct.calcsize("@bq") % struct.calcsize("@q"), 0)

    def test_padding_report_sum_matches_calcsize(self):
        for fmt in ["@bi", "@bq", "@?h", "@ib0i"]:
            with self.subTest(fmt=fmt):
                report = padding_report(fmt)
                total = sum(size + padding for _, size, _, padding in report)
                self.assertEqual(total, struct.calcsize(fmt))


class RoundtripTest(unittest.TestCase):
    """고정 형식(<)으로 인코딩·디코딩 왕복을 확인한다."""

    def test_sensor_roundtrip(self):
        data = SensorData(kind=1, count=1000, ratio=0.5)
        encoded = encode_sensor(data, SENSOR_RECORD_LITTLE)
        decoded = decode_sensor(encoded, SENSOR_RECORD_LITTLE)
        self.assertEqual(decoded.kind, data.kind)
        self.assertEqual(decoded.count, data.count)
        self.assertEqual(decoded.ratio, data.ratio)

    def test_little_endian_pack_bytes(self):
        self.assertEqual(struct.pack("<bi", 1, 2).hex(), "0102000000")
        self.assertEqual(struct.pack("<H", 0x1234).hex(), "3412")
        self.assertEqual(struct.pack("<I", 0x12345678).hex(), "78563412")


class FormatComparisonTest(unittest.TestCase):
    """같은 데이터를 세 형식으로 패킹했을 때 차이를 확인한다."""

    def test_compare_format_sizes(self):
        sizes = compare_format_sizes()
        self.assertIn("native(@)", sizes)
        self.assertIn("standard(=)", sizes)
        self.assertIn("little(<)", sizes)
        self.assertGreaterEqual(sizes["native(@)"], sizes["little(<)"])
        self.assertEqual(sizes["standard(=)"], sizes["little(<)"])

    def test_all_formats_produce_valid_bytes(self):
        data = SensorData(kind=1, count=100, ratio=0.1)
        for fmt in [SENSOR_RECORD_NATIVE, SENSOR_RECORD_STANDARD, SENSOR_RECORD_LITTLE]:
            with self.subTest(fmt=fmt):
                encoded = encode_sensor(data, fmt)
                self.assertEqual(len(encoded), struct.calcsize(fmt))
                decoded = decode_sensor(encoded, fmt)
                self.assertEqual(decoded.kind, data.kind)


class RangeErrorTest(unittest.TestCase):
    """범위 밖 값이 거절되는지 확인한다."""

    def test_signed_short_range(self):
        struct.pack("<h", 32767)
        struct.pack("<h", -32768)
        with self.assertRaisesRegex(struct.error, r"'h' format requires"):
            struct.pack("<h", 40000)
        with self.assertRaisesRegex(struct.error, r"'h' format requires"):
            struct.pack("<h", -32769)

    def test_unsigned_ranges(self):
        with self.assertRaisesRegex(struct.error, r"'B' format requires"):
            struct.pack("<B", 256)
        with self.assertRaisesRegex(struct.error, r"'B' format requires"):
            struct.pack("<B", -1)
        with self.assertRaisesRegex(struct.error, r"'H' format requires"):
            struct.pack("<H", -1)
        with self.assertRaisesRegex(struct.error, r"'I' format requires"):
            struct.pack("<I", -1)

    def test_signed_int_range(self):
        with self.assertRaisesRegex(struct.error, r"'i' format requires"):
            struct.pack("<i", 2**31)
        with self.assertRaisesRegex(struct.error, r"'i' format requires"):
            struct.pack("<i", -(2**31) - 1)


class TypeErrorTest(unittest.TestCase):
    """정수가 아닌 값이 거절되는지 확인한다."""

    def test_float_to_int_format(self):
        with self.assertRaisesRegex(struct.error, r"required argument is not an integer"):
            struct.pack("<h", 1.5)

    def test_string_to_bool_format_converts_silently(self):
        # 표준 struct는 조용히 True로 변환한다
        result = struct.pack("<?", "x")
        self.assertEqual(result, b"\x01")


class ArgumentCountTest(unittest.TestCase):
    """인자 수 불일치가 거절되는지 확인한다."""

    def test_too_few_arguments(self):
        with self.assertRaisesRegex(struct.error, r"pack expected 2 items"):
            struct.pack("<HH", 1)

    def test_too_many_arguments(self):
        with self.assertRaisesRegex(struct.error, r"pack expected 2 items"):
            struct.pack("<HH", 1, 2, 3)


class BufferLengthTest(unittest.TestCase):
    """버퍼 길이 불일치가 거절되는지 확인한다."""

    def test_unpack_short_buffer(self):
        with self.assertRaisesRegex(struct.error, r"unpack requires a buffer of 4 bytes"):
            struct.unpack("<I", b"\x01\x02\x03")

    def test_unpack_long_buffer(self):
        with self.assertRaisesRegex(struct.error, r"unpack requires a buffer of 4 bytes"):
            struct.unpack("<I", b"\x01\x02\x03\x04\x05")

    def test_unpack_from_offset(self):
        result = struct.unpack_from("<H", b"\xff\x02\x00", 1)
        self.assertEqual(result, (2,))

    def test_unpack_from_short_buffer(self):
        with self.assertRaisesRegex(struct.error, r"unpack_from requires a buffer of at least"):
            struct.unpack_from("<H", b"\x01", 0)

    def test_iter_unpack_non_multiple(self):
        with self.assertRaisesRegex(
            struct.error, r"iterative unpacking requires a buffer of a multiple of 2 bytes"
        ):
            list(struct.iter_unpack("<H", b"\x01\x00\x02"))


class FloatPrecisionTest(unittest.TestCase):
    """float 정밀도 손실과 오버플로를 확인한다."""

    def test_float_precision_loss(self):
        packed = struct.pack("<f", 0.1)
        unpacked = struct.unpack("<f", packed)[0]
        self.assertNotEqual(unpacked, 0.1)
        self.assertAlmostEqual(unpacked, 0.10000000149011612, places=15)

    def test_double_preserves_precision(self):
        packed = struct.pack("<d", 0.1)
        unpacked = struct.unpack("<d", packed)[0]
        self.assertEqual(unpacked, 0.1)

    def test_half_float_overflow(self):
        with self.assertRaises(OverflowError):
            struct.pack("<e", 70000.0)

    def test_float_overflow(self):
        with self.assertRaises(OverflowError):
            struct.pack("<f", 1e39)


class StringFormatTest(unittest.TestCase):
    """s 형식의 잘림, NUL 채움, str 거절을 확인한다."""

    def test_string_truncation(self):
        result = struct.pack("<4s", b"abcdef")
        self.assertEqual(result, b"abcd")

    def test_string_nul_padding(self):
        result = struct.pack("<4s", b"ab")
        self.assertEqual(result, b"ab\x00\x00")

    def test_string_rejects_str(self):
        with self.assertRaisesRegex(struct.error, r"argument for 's' must be a bytes object"):
            struct.pack("<4s", "ab")


class ByteorderConfusionTest(unittest.TestCase):
    """바이트 순서 혼동이 조용히 값을 바꾸는 것을 확인한다."""

    def test_little_as_big_changes_value(self):
        little_bytes = struct.pack("<I", 1)
        value_as_big = struct.unpack(">I", little_bytes)[0]
        self.assertEqual(value_as_big, 16777216)

    def test_demonstrate_function(self):
        result = demonstrate_byteorder_confusion(1)
        self.assertEqual(result["original"], 1)
        self.assertEqual(result["little_as_big"], 16777216)
        self.assertNotEqual(result["little_bytes"], result["big_bytes"])


class FrameHeaderTest(unittest.TestCase):
    """검증 헤더의 정상 경로와 경계를 확인한다."""

    def test_header_struct_size(self):
        self.assertEqual(FRAME_HEADER_STRUCT.size, 8)

    def test_encode_decode_roundtrip(self):
        payload = b"Hello, world!"
        frame = encode_frame(payload, version=1, flags=0x42)
        version, flags, decoded_payload = decode_frame(frame)
        self.assertEqual(version, 1)
        self.assertEqual(flags, 0x42)
        self.assertEqual(decoded_payload, payload)

    def test_empty_payload(self):
        frame = encode_frame(b"")
        self.assertEqual(len(frame), FRAME_HEADER_STRUCT.size)
        version, flags, payload = decode_frame(frame)
        self.assertEqual(payload, b"")

    def test_max_payload_length(self):
        payload = b"x" * FRAME_MAX_PAYLOAD
        frame = encode_frame(payload)
        _, _, decoded = decode_frame(frame)
        self.assertEqual(len(decoded), FRAME_MAX_PAYLOAD)

    def test_oversized_payload_rejected(self):
        with self.assertRaisesRegex(FrameError, r"payload 길이가 최대값을 초과"):
            encode_frame(b"x" * (FRAME_MAX_PAYLOAD + 1))

    def test_magic_mismatch(self):
        frame = encode_frame(b"test")
        bad = b"XXXX" + frame[4:]
        with self.assertRaisesRegex(FrameError, r"magic 불일치"):
            decode_frame(bad)

    def test_unknown_version(self):
        frame = encode_frame(b"test", version=1)
        bad = frame[:4] + struct.pack("BBH", 99, 0, len(b"test")) + b"test"
        with self.assertRaisesRegex(FrameError, r"알 수 없는 version"):
            decode_frame(bad)

    def test_buffer_shorter_than_header(self):
        with self.assertRaisesRegex(FrameError, r"헤더보다 짧다"):
            decode_frame(b"FRME123")

    def test_empty_buffer(self):
        with self.assertRaisesRegex(FrameError, r"헤더보다 짧다"):
            decode_frame(b"")

    def test_payload_shorter_than_declared(self):
        frame = encode_frame(b"12345")
        with self.assertRaisesRegex(FrameError, r"payload가 짧다"):
            decode_frame(frame[:-1])

    def test_payload_longer_than_declared(self):
        frame = encode_frame(b"12345")
        with self.assertRaisesRegex(FrameError, r"payload가 길다"):
            decode_frame(frame + b"X")

    def test_version_range(self):
        with self.assertRaisesRegex(FrameError, r"version은 1~255 범위"):
            encode_frame(b"", version=0)
        with self.assertRaisesRegex(FrameError, r"version은 1~255 범위"):
            encode_frame(b"", version=256)

    def test_flags_range(self):
        with self.assertRaisesRegex(FrameError, r"flags는 0~255 범위"):
            encode_frame(b"", flags=-1)
        with self.assertRaisesRegex(FrameError, r"flags는 0~255 범위"):
            encode_frame(b"", flags=256)


class RecordArrayTest(unittest.TestCase):
    """레코드 배열 읽기와 나머지 바이트 거절을 확인한다."""

    def test_read_multiple_records(self):
        records = [(1, 10), (2, 20), (3, 30)]
        packed = b"".join(struct.pack("<bH", k, v) for k, v in records)
        decoded = read_record_array(packed, "<bH")
        self.assertEqual(decoded, records)

    def test_empty_array(self):
        decoded = read_record_array(b"", "<bH")
        self.assertEqual(decoded, [])

    def test_remainder_rejected(self):
        records = [(1, 10), (2, 20)]
        packed = b"".join(struct.pack("<bH", k, v) for k, v in records)
        with self.assertRaisesRegex(ValueError, r"오프셋 6에서 1바이트 남음"):
            read_record_array(packed + b"\x00", "<bH")

    def test_offset_reported_in_error(self):
        packed = struct.pack("<HH", 1, 2) + b"\xff"
        with self.assertRaisesRegex(ValueError, r"오프셋 4에서"):
            read_record_array(packed, "<HH")


class PaddingReportTest(unittest.TestCase):
    """패딩 계산 함수를 확인한다."""

    def test_simple_format(self):
        report = padding_report("<bi")
        self.assertEqual(len(report), 2)
        self.assertEqual(report[0][0], "b")
        self.assertEqual(report[1][0], "i")
        self.assertEqual(report[0][2], 0)

    def test_native_padding(self):
        report = padding_report("@bi")
        # 플랫폼마다 다르지만 패딩 합은 calcsize와 일치해야 한다
        total = sum(size + padding for _, size, _, padding in report)
        self.assertEqual(total, struct.calcsize("@bi"))

    def test_repeat_count(self):
        report = padding_report("<3h")
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0][0], "3h")
        self.assertEqual(report[0][1], 6)

    def test_padding_byte_x(self):
        report = padding_report("<bxH")
        self.assertEqual(len(report), 3)
        self.assertEqual(report[1][0], "x")

    def test_zero_field_alignment(self):
        report = padding_report("@ib0i")
        total = sum(size + padding for _, size, _, padding in report)
        self.assertEqual(total, struct.calcsize("@ib0i"))


class PerformanceComparisonTest(unittest.TestCase):
    """성능 비교 함수가 실행 가능한지 확인한다."""

    def test_comparison_runs(self):
        result = performance_comparison("<iHd", (100, 200, 0.5), n=1000)
        self.assertIn("struct.pack", result)
        self.assertIn("Struct.pack", result)
        self.assertIn("ratio", result)
        self.assertGreater(result["struct.pack"], 0)
        self.assertGreater(result["Struct.pack"], 0)
        self.assertGreater(result["ratio"], 0)

    def test_produces_same_bytes(self):
        values = (100, 200, 0.5)
        direct = struct.pack("<iHd", *values)
        compiled = struct.Struct("<iHd").pack(*values)
        self.assertEqual(direct, compiled)


if __name__ == "__main__":
    unittest.main()
