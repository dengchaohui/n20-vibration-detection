import serial
import time
import argparse
import struct

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='n20_data.csv')
parser.add_argument('--infer_output', default='n20_infer.csv')
parser.add_argument('--raw_dump', default='/tmp/serial_raw.bin')
parser.add_argument('--duration', type=int, default=30)
parser.add_argument('--port', default='/dev/ttyACM0')
parser.add_argument('--baud', type=int, default=921600)
args = parser.parse_args()

OUTPUT = args.output
INFER_OUTPUT = args.infer_output
RAW_DUMP = args.raw_dump
DURATION = args.duration
PORT = args.port
BAUDRATE = args.baud

print(f'串口: {PORT} @ {BAUDRATE}')
print(f'时长: {DURATION} 秒')
print(f'数据输出: {OUTPUT}')
print(f'推理输出: {INFER_OUTPUT}')
print(f'原始字节: {RAW_DUMP}')

DATA_FRAME_SIZE = 13
INFER_FRAME_SIZE = 16

ser = serial.Serial(PORT, BAUDRATE, timeout=1)
time.sleep(2)
ser.reset_input_buffer()

raw_dump = open(RAW_DUMP, 'wb')

print('发送启动命令...')
ser.write(b's')
ser.flush()
time.sleep(0.5)
ser.reset_input_buffer()

start = time.time()
buf = b''
data_lines = []
infer_lines = []

print('开始采集...')

try:
    while time.time() - start < DURATION:
        chunk = ser.read(4096)
        if not chunk:
            continue

        raw_dump.write(chunk)
        buf += chunk

        while True:
            if len(buf) < 2:
                break

            if buf[0] == 0xAA and buf[1] == 0x55:
                if len(buf) < DATA_FRAME_SIZE:
                    break
                frame = buf[:DATA_FRAME_SIZE]
                cs = frame[12]
                calc = 0
                for b in frame[:12]:
                    calc ^= b
                if cs != calc:
                    buf = buf[1:]
                    continue
                ts, x, y, z = struct.unpack('<IHHH', frame[2:12])
                data_lines.append(f'{ts},{x},{y},{z}')
                buf = buf[DATA_FRAME_SIZE:]

            elif buf[0] == 0xBB and buf[1] == 0x66:
                if len(buf) < INFER_FRAME_SIZE:
                    break
                frame = buf[:INFER_FRAME_SIZE]
                cs = frame[15]
                calc = 0
                for b in frame[:15]:
                    calc ^= b
                if cs != calc:
                    buf = buf[1:]
                    continue
                ts = struct.unpack('<I', frame[2:6])[0]
                win_start_ts = struct.unpack('<I', frame[6:10])[0]
                prob = struct.unpack('<f', frame[10:14])[0]
                label = frame[14]
                infer_lines.append(f'{ts},{win_start_ts},{prob:.6f},{label}')
                buf = buf[INFER_FRAME_SIZE:]

            else:
                buf = buf[1:]

except KeyboardInterrupt:
    print('\n手动中断')

ser.close()
raw_dump.close()

with open(OUTPUT, 'w') as f:
    f.write('time_us,x,y,z\n')
    for line in data_lines:
        f.write(line + '\n')

with open(INFER_OUTPUT, 'w') as f:
    f.write('time_us,window_start_us,prob,label\n')
    for line in infer_lines:
        f.write(line + '\n')

print(f'数据样本: {len(data_lines)}')
print(f'推理次数: {len(infer_lines)}')

if len(data_lines) > 1:
    ts = [int(l.split(',')[0]) for l in data_lines]
    diffs = [ts[i+1] - ts[i] for i in range(len(ts) - 1)]
    diffs = [d for d in diffs if d > 0]
    if diffs:
        print(f'数据间隔: min={min(diffs)} us, max={max(diffs)} us, '
              f'mean={sum(diffs)/len(diffs):.1f} us')
        print(f'采样率: {1e6 / (sum(diffs)/len(diffs)):.1f} Hz')
        base = 625
        lost = sum(max(0, round(d / base) - 1) for d in diffs)
        print(f'估算丢数: {lost} 个')
