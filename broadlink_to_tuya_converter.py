import io
import base64
import json
import sys
import re
import argparse
import os
from datetime import datetime
from bisect import bisect
from struct import pack
from math import ceil

# === Paramètres de chemins par défaut ===
DEFAULT_SOURCE_DIR = "/config/custom_components/smartir/codes/climate/"
DEFAULT_DEST_DIR = "/config/custom_components/smartir/custom_codes/climate/"

# Constantes
BRDLNK_UNIT = 269 / 8192
LOG_FILENAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "broadlink_to_tuya.log")

# Utilitaire pour filtrer les timings
flt = lambda x: [i for i in x if i < 65535]

# Détection de chaîne base64 Broadlink plausible
_b64_re = re.compile(r'^[A-Za-z0-9+/]+={0,2}$')
def looks_like_base64_broadlink(s: str) -> bool:
    if not isinstance(s, str):
        return False
    if len(s) < 8:
        return False
    if len(s) % 4 != 0 and '=' not in s:
        return False
    return bool(_b64_re.match(s))

def encode_ir(command: str) -> str:
    # command = base64 Broadlink string
    signal = flt(get_raw_from_broadlink(base64.b64decode(command).hex()))
    payload = b''.join(pack('<H', t) for t in signal)
    compress(out := io.BytesIO(), payload, level=2)
    payload = out.getvalue()
    return base64.encodebytes(payload).decode('ascii').replace('\n', '')

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
    '''
    Takes a byte string and outputs a compressed "Tuya stream".
    Implemented compression levels:
    0 - copy over (no compression, 3.1% overhead)
    1 - eagerly use first length-distance pair found (linear)
    2 - eagerly use best length-distance pair found
    3 - optimal compression (n^3)
    '''
    if level == 0:
        return emit_literal_blocks(out, data)

    W = 2**13
    L = 255+9
    distance_candidates = lambda: range(1, min(pos, W) + 1)

    def find_length_for_distance(start: int) -> int:
        length = 0
        limit = min(L, len(data) - pos)
        while length < limit and data[pos + length] == data[start + length]:
            length += 1
        return length
    find_length_candidates = lambda: (
        (find_length_for_distance(pos - d), d) for d in distance_candidates()
    )
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
            idxs = (idx+i for i in (+1,-1)) # try +1 first
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

def get_raw_from_broadlink(string):
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

def process_commands(filename, controller):
    with open(filename, 'r') as file:
        data = json.load(file)

    ignored_keys = []

    def process_commands_recursively(commands):
        processed_commands = {}
        for key, value in commands.items():
            if isinstance(value, str):
                if looks_like_base64_broadlink(value):
                    processed_commands[key] = encode_ir(value)
                else:
                    processed_commands[key] = value
                    ignored_keys.append(key)
            elif isinstance(value, dict):
                processed_commands[key] = process_commands_recursively(value)
            else:
                processed_commands[key] = value
                ignored_keys.append(key)
        return processed_commands

    data['commands'] = process_commands_recursively(data.get('commands', {}))
    data['supportedController'] = controller
    data['commandsEncoding'] = 'Raw'
    return json.dumps(data, indent=2), ignored_keys

def log_summary(source, destination, ignored_keys):
    with open(LOG_FILENAME, 'w') as log_file:
        log_file.write(f"Horodatage : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(f"Fichier source : {source}\n")
        log_file.write(f"Fichier destination : {destination}\n")
        log_file.write(f"Clés ignorées ({len(ignored_keys)}) :\n")
        for key in ignored_keys:
            log_file.write(f" - {key}\n")

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convertisseur Broadlink vers Tuya JSON\n"
            f"Chemin source par défaut : {DEFAULT_SOURCE_DIR}\n"
            f"Chemin destination par défaut : {DEFAULT_DEST_DIR}\n\n"
            "UTILISATION :\n"
            "  python3 broadlink_to_tuya_converter.py <fichier_source.json> [<fichier_destination.json>] --controller <type>\n\n"
            "OPTIONS :\n"
            "  fichier_source.json       Obligatoire. Nom du fichier JSON source (avec ou sans chemin).\n"
            "  fichier_destination.json  Optionnel. Nom du fichier JSON destination (seulement nom, sans chemin).\n"
            "                            Si absent, le fichier destination aura le même nom que le fichier source,\n"
            "                            et sera sauvegardé dans le répertoire de destination par défaut.\n"
            "  --controller             Obligatoire. Spécifie le type de contrôleur. Valeurs acceptées : MQTT ou UFOR11.\n"
            "  --help                   Affiche cette aide.\n\n"
            "DESCRIPTION :\n"
            "Ce script lit un fichier JSON contenant des commandes IR encodées au format Broadlink, "
            "les convertit au format Tuya, et sauvegarde le résultat dans un répertoire de destination. "
            "Un fichier de log est créé à côté du script avec la liste des clés ignorées et les chemins des fichiers traités.\n\n"
            "COMPORTEMENT :\n"
            " - Si le fichier de destination existe, l'utilisateur peut choisir de l'écraser ou non.\n"
            " - Les fichiers source et destination doivent exister et être valides.\n"
            " - Le paramètre --controller doit être strictement 'MQTT' ou 'UFOR11'.\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("source_filename", help="Nom du fichier JSON source (sans chemin ou avec chemin complet)")
    parser.add_argument("dest_filename", nargs='?', default=None, help="Nom optionnel du fichier JSON destination (sans chemin)")
    parser.add_argument("--controller", required=True, help="Type de contrôleur : MQTT ou UFOR11")
    args = parser.parse_args()

    # Construction du chemin source complet
    if not os.path.isabs(args.source_filename):
        source_path = os.path.join(DEFAULT_SOURCE_DIR, args.source_filename)
    else:
        source_path = args.source_filename

    # Construction du chemin destination complet
    if args.dest_filename:
        dest_path = os.path.join(DEFAULT_DEST_DIR, args.dest_filename)
    else:
        dest_path = os.path.join(DEFAULT_DEST_DIR, os.path.basename(source_path))

    # Validation contrôleur
    if args.controller not in ("MQTT", "UFOR11"):
        print("\033[91mERREUR : Contrôleur invalide. Valeurs acceptées : MQTT, UFOR11.\033[0m")
        sys.exit(1)

    # Vérification source
    if not os.path.isfile(source_path):
        print(f"\033[91mERREUR : Fichier source introuvable : {source_path}\033[0m")
        sys.exit(1)
    try:
        with open(source_path, 'r') as f:
            json.load(f)
    except Exception:
        print("\033[91mERREUR : Fichier source invalide ou non lisible en JSON.\033[0m")
        sys.exit(1)

    # Vérification destination
    dest_dir = os.path.dirname(dest_path)
    if not os.path.isdir(dest_dir):
        print(f"\033[91mERREUR : Chemin de destination invalide : {dest_dir}\033[0m")
        sys.exit(1)
    if os.path.exists(dest_path):
        overwrite = input(f"Le fichier {dest_path} existe déjà. Écraser ? (o/N) : ").strip().lower()
        if overwrite != "o":
            print("\033[91mAnnulation par l'utilisateur.\033[0m")
            sys.exit(0)

    # Traitement
    try:
        result_json, ignored = process_commands(source_path, args.controller)
        with open(dest_path, 'w') as dest_file:
            dest_file.write(result_json)
        log_summary(source_path, dest_path, ignored)
        print(f"\033[92mSuccès\033[0m : Conversion terminée.")
    except Exception as e:
        print(f"\033[91mERREUR : {e}\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()
