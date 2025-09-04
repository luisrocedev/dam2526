#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Explica el contenido de cada carpeta (recursivamente) usando Ollama.
- Construye un árbol GLOBAL (excluyendo .git) como contexto.
- Para cada subcarpeta (excluyendo .git), solicita a Ollama una explicación
  en español, sin código y agnóstica de tecnología.
- Guarda "Contenidos básicos.md" en cada carpeta.
- Muestra por consola el PROMPT enviado y la RESPUESTA recibida.

Requisitos:
  - Python 3.8+
  - requests  (pip install requests)
  - Ollama en ejecución (http://localhost:11434) y modelo descargado
    (p. ej. `ollama pull qwen2.5-coder:7b`)
Uso:
  python3 explica_carpetas_con_ollama.py
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import List, Iterable
import requests

# ---------------------- CONFIGURACIÓN ----------------------

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.2"))
NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "65536"))

# Excluir directorios en cualquier nivel
EXCLUDE_DIRS = {".git"}  # añade aquí p.ej. "node_modules", ".venv", "dist", "build", etc.

# Pausa entre peticiones
SLEEP_BETWEEN_REQUESTS = float(os.environ.get("OLLAMA_SLEEP", "0.5"))

# Nombre del archivo de salida en cada carpeta
OUTPUT_FILENAME = "Contenidos básicos.md"

# ---------------------- UTILIDADES ----------------------


def is_excluded_dir(path: Path) -> bool:
    """Devuelve True si el nombre de la carpeta coincide con alguna exclusión."""
    return path.name in EXCLUDE_DIRS


def build_tree(root: Path) -> str:
    """
    Construye un árbol de texto del directorio `root`, excluyendo carpetas en EXCLUDE_DIRS.
    """
    lines: List[str] = [root.name + "/"]

    def _walk(dir_path: Path, prefix: str = ""):
        try:
            entries = sorted(
                (e for e in dir_path.iterdir() if not (e.is_dir() and is_excluded_dir(e))),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            return

        total = len(entries)
        for i, entry in enumerate(entries):
            connector = "└── " if i == total - 1 else "├── "
            lines.append(prefix + connector + entry.name + ("/" if entry.is_dir() else ""))
            if entry.is_dir():
                extension = "    " if i == total - 1 else "│   "
                _walk(entry, prefix + extension)

    _walk(root)
    return "\n".join(lines)


def iter_all_subdirs(root: Path) -> Iterable[Path]:
    """
    Itera todas las subcarpetas bajo `root` (recursivo), excluyendo cualquier
    directorio cuyo nombre esté en EXCLUDE_DIRS en cualquier nivel.
    """
    for dirpath, dirnames, _filenames in os.walk(root):
        # Filtra in-place dirnames para que os.walk no entre en excluidos
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for d in dirnames:
            yield Path(dirpath) / d


def chat_ollama(model: str, system: str, user: str) -> str:
    """
    Llama a /api/chat de Ollama con mensajes system+user.
    Devuelve el contenido de la respuesta en texto.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {
            "temperature": TEMPERATURE,
            "num_ctx": NUM_CTX,
        },
        "stream": False,
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=600)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict) and "message" in data and "content" in data["message"]:
        return data["message"]["content"].strip()

    return json.dumps(data, ensure_ascii=False, indent=2)


# ---------------------- LÓGICA PRINCIPAL ----------------------


def main():
    base = Path(__file__).resolve().parent

    # 1) Construir árbol global
    tree_text = build_tree(base)

    # 2) Recopilar TODAS las subcarpetas (recursivo), excluyendo .git y similares
    target_dirs = list(iter_all_subdirs(base))
    if not target_dirs:
        print("No se han encontrado subcarpetas objetivo (excluyendo directorios ignorados).")
        print("Directorio base:", base)
        sys.exit(0)

    # 3) Mensaje del sistema (reglas, agnóstico de tecnología)
    system_msg = (
        "Eres un asistente experto en organización de proyectos y documentación técnica. "
        "Redacta explicaciones claras, concisas y didácticas sobre el contenido de una carpeta. "
        "REQUISITOS OBLIGATORIOS:\n"
        "1) Responde en español.\n"
        "2) NO incluyas fragmentos de código; solo párrafos en prosa.\n"
        "3) Mantén la explicación agnóstica de tecnología: no menciones nombres de lenguajes, "
        "frameworks o herramientas concretas.\n"
        "4) Enfócate en propósito, estructura, tipos de artefactos esperables, flujos habituales, "
        "y buenas prácticas generales (organización, pruebas, configuración, documentación, automatización, etc.).\n"
    )

    # Contexto global (árbol)
    context_header = (
        "A continuación tienes el árbol de directorios GLOBAL (contexto) del entorno actual. "
        "Úsalo para comprender la organización general:\n\n"
        "```\n" + tree_text + "\n```\n"
    )

    # 4) Procesar cada carpeta
    for d in target_dirs:
        rel = d.relative_to(base)
        user_prompt = (
            f"{context_header}\n"
            f"Carpeta a documentar: `{rel}`.\n\n"
            "Objetivo: redacta un documento breve de 'Contenidos básicos' para esta carpeta. "
            "Cubre su propósito, responsabilidades principales, cómo se integra con el resto del proyecto, "
            "qué contenidos suele albergar, flujos de trabajo habituales, y recomendaciones generales de calidad "
            "(organización, validaciones, pruebas, configuración, observabilidad y documentación). "
            "Recuerda: en español, sin código, y sin mencionar tecnologías concretas.\n"
        )

        # Mostrar PROMPT por consola
        print("\n" + "=" * 100)
        print(f"[PROMPT para] {rel}")
        print("-" * 100)
        print(user_prompt)

        try:
            answer = chat_ollama(MODEL, system_msg, user_prompt)
        except requests.RequestException as e:
            print(f"[!] Error al llamar a Ollama para {rel}: {e}")
            continue

        # Mostrar RESPUESTA por consola
        print("-" * 100)
        print(f"[RESPUESTA de] {rel}")
        print("-" * 100)
        print(answer)
        print("=" * 100)

        # Guardar en 'Contenidos básicos.md'
        out_path = d / OUTPUT_FILENAME
        try:
            out_path.write_text(answer + "\n", encoding="utf-8")
            print(f"[✓] Guardado: {out_path}")
        except Exception as e:
            print(f"[!] No se pudo escribir {out_path}: {e}")

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    print("\nTerminado.")


if __name__ == "__main__":
    main()
