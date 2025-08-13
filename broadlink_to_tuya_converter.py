# Code original : https://gist.github.com/svyatogor/7839d00303998a9fa37eb48494dd680f?permalink_comment_id=5153002#gistcomment-5153002

import io
import base64
import json
import sys
from bisect import bisect
from struct import pack, unpack
from math import ceil
from pathlib import Path

# Constantes
BRDLNK_UNIT = 269 / 8192  # Broadlink timing unit (~32.84 µs)

# MAIN API
filter_ir = lambda x: [i for i in x if i < 65535]  # évite les valeurs Broadlink inutiles

def encode_ir(command: str) -> str:
    """Encode une commande IR Broadlink en format compressé Tuya."""
    signal = filter_ir(get_raw_from_broadlink(base64.b64decode(command).hex()))
    payload = b''.join(pack('<H', t) for t in signal)
    compress(out := io.BytesIO(), payload, level=2)
    return base64.b64encode(out.getvalue()).decode('ascii')


# COMPRESSION

def emit_literal_blocks(out: io.FileIO, data: bytes):
    for i in range(0, len(data), 32):
        emit_literal_block(out, data[i:i+32])

def emit_literal_block(out: io.FileIO, data: bytes):
    length = len(data) - 1
    assert 0 <= length < (1 << 5)
    out.write(bytes([length]))
    out.write(data)

def emit_distance_block(out: io.FileIO, length: int, distance: int):
    distance -= 1
    assert 0 <= distance < (1 << 13)
    length -= 2
    assert length > 0
    block = bytearray()
    if length >= 7:
        assert length - 7 < (1 << 8)
        block.append(length - 7)
        length = 7
    block.insert(0, length << 5 | distance >> 8)
    block.append(distance & 0xFF)
    out.write(block)

def compress(out: io.FileIO, data: bytes, level=2):
    """
    Compresse un flux en "Tuya stream".
    Niveaux de compression :
    0 - copie brute
    1 - premier couple longueur-distance trouvé
    2 - meilleur couple longueur-distance trouvé
    3 - compression optimale (n^3)
    """
    if level == 0:
        return emit_literal_blocks(out, data)

    W = 2**13
    L = 255 + 9
    distance_candidates = lambda: range(1, min(pos, W) + 1)

    def find_length_for_distance(start: int) -> int:
        length = 0
        limit = min(L, len(data) - pos)
        while length < limit and data[pos + length] == data[start + length]:
            length += 1
        return length

    find_length_candidates = lambda: ((find_length_for_distance(pos - d), d) for d in distance_candidates())
    find_length_cheap = lambda: next((c for c in find_length_candidates() if c[0] >= 3), None)
    find_length_max = lambda: max(find_length_candidates(), key=lambda c: (c[0], -c[1]), default=None)

    if level >= 2:
        suffixes = []
        next_pos = 0
        key = lambda n: data[n:]
        find_idx = lambda n: bisect(suffixes, key(n), key=key)

        def distance_candidates():
            nonlocal next_pos
            while next_pos <= pos:
                if len(suffixes) == W:
                    suffixes.pop(find_idx(next_pos - W))
                suffixes.insert(idx := find_idx(next_pos), next_pos)
                next_pos += 1
            idxs = (idx + i for i in (+1, -1))
            return (pos - suffixes[i] for i in idxs if 0 <= i < len(suffixes))

    if level <= 2:
        find_length = {1: find_length_cheap, 2: find_length_max}[level]
        block_start = pos = 0
        while pos < len(data):
            if (c := find_length()) and c[0] >= 3:
                emit_literal_blocks(out, data[block_start:pos])
                emit_distance_block(out, c[0], c[1])
                pos += c[0]
                block_start = pos
            else:
                pos += 1
        emit_literal_blocks(out, data[block_start:pos])
        return

    predecessors = [(0, None, None)] + [None] * len(data)

    def put_edge(cost, length, distance):
        npos = pos + length
        cost += predecessors[pos][0]
        current = predecessors[npos]
        if not current or cost < current[0]:
            predecessors[npos] = cost, length, distance

    for pos in range(len(data)):
        if c := find_length_max():
            for l in range(3, c[0] + 1):
                put_edge(2 if l < 9 else 3, l, c[1])
        for l in range(1, min(32, len(data) - pos) + 1):
            put_edge(1 + l, l, 0)

    blocks = []
    pos = len(data)
    while pos > 0:
        _, length, distance = predecessors[pos]
        pos -= length
        blocks.append((pos, length, distance))

    for pos, length, distance in reversed(blocks):
        if not distance:
            emit_literal_block(out, data[pos:pos + length])
        else:
            emit_distance_block(out, length, distance)


def get_raw_from_broadlink(string: str):
    """Décode un payload Broadlink en liste de timings."""
    dec = []
    unit = BRDLNK_UNIT
    length = int(string[6:8] + string[4:6], 16)

    i = 8
    while i < length * 2 + 8:
        hex_value = string[i:i+2]
        if hex_value == "00":
            hex_value = string[i+2:i+4] + string[i+4:i+6]
            i += 4
        dec.append(ceil(int(hex_value, 16) / unit))
        i += 2
    return dec


def process_commands_recursively(commands):
    processed = {}
    for key, value in commands.items():
        if isinstance(value, str):
            processed[key] = encode_ir(value)
        elif isinstance(value, dict):
            processed[key] = process_commands_recursively(value)
        else:
            processed[key] = value
    return processed


def process_commands(filename: str):
    file_path = Path(filename)
    if not file_path.exists():
        sys.exit(f"Erreur : fichier introuvable -> {file_path}")

    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
    except json.JSONDecodeError as e:
        sys.exit(f"Erreur JSON : {e}")

    data['commands'] = process_commands_recursively(data.get('commands', {}))
    data['supportedController'] = 'MQTT'
    data['commandsEncoding'] = 'Raw'
    return json.dumps(data, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage : python script.py <fichier.json>")
    print(process_commands(sys.argv[1]))
