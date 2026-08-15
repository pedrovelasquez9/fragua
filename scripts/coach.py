"""Historial de recomendaciones editoriales, para saber si el contenido mejora.

    python coach.py                                    informe: tendencia y reincidencias
    python coach.py log --file X --topic "..." \\
           --applied hook-al-inicio,dato-concreto \\
           --pending anecdota-personal                 registra un vídeo
    python coach.py checks                             lista los criterios evaluables

Una sugerencia en texto libre no se puede comparar entre vídeos: «mejora el
gancho» dicho en marzo y en agosto son cadenas distintas. Por eso los criterios
son un catálogo cerrado con identificador, y lo que se guarda por vídeo es qué
identificadores se cumplieron y cuáles no.

Se guarda en `~/.fragua/coaching.json`, fuera del plugin, para que sobreviva a
las actualizaciones.
"""
import argparse
from datetime import date

from common import ASSETS_CONFIG, read_json, write_json

HISTORY = ASSETS_CONFIG.parent / "coaching.json"

# Criterios evaluables. Añadir uno nuevo no invalida el historial: los vídeos
# antiguos simplemente no lo mencionan.
CHECKS = {
    "hook-al-inicio":      "La frase más fuerte está en los primeros 5 segundos",
    "anecdota-personal":   "Cuenta al menos una experiencia propia, no sólo el principio",
    "dato-concreto":       "Hay una cifra, una fecha o un hecho verificable",
    "contrapunto":         "Reconoce el matiz o la objeción antes de que la hagan",
    "cta-especifico":      "El cierre pide una anécdota concreta, no una opinión",
    "sin-tomas-repetidas": "No hay tomas dobles, tropiezos ni falsos arranques",
    "cierre-limpio":       "Termina en el remate, sin relleno detrás",
    "registro-consistente": "No mezcla tú y ustedes",
    "termino-propio":      "Si acuña un concepto, lo explica sin darlo por sabido",
}

# A partir de aquí una recomendación repetida deja de ser un apunte y pasa a ser
# el tema del que hay que hablar.
INSISTENCE_THRESHOLD = 3


def load():
    return read_json(HISTORY) if HISTORY.exists() else {"videos": []}


def save(data):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    write_json(HISTORY, data)


def split_ids(raw):
    """'a,b , c' -> ['a', 'b', 'c'], validando contra el catálogo."""
    ids = [piece.strip() for piece in (raw or "").split(",") if piece.strip()]
    unknown = [i for i in ids if i not in CHECKS]
    if unknown:
        raise SystemExit(f"criterios desconocidos: {', '.join(unknown)}\n"
                         f"Disponibles: {', '.join(CHECKS)}")
    return ids


def streaks(videos):
    """Por criterio: veces cumplido, veces pendiente y racha pendiente actual."""
    stats = {}
    for check in CHECKS:
        applied = sum(1 for v in videos if check in v.get("applied", []))
        pending = sum(1 for v in videos if check in v.get("pending", []))
        run = 0
        for video in reversed(videos):
            if check in video.get("pending", []):
                run += 1
            elif check in video.get("applied", []):
                break
        stats[check] = {"applied": applied, "pending": pending, "run": run}
    return stats


def report(data):
    videos = data["videos"]
    if not videos:
        print("Sin historial todavía. Registra el primer vídeo con  coach.py log")
        return

    print(f"{len(videos)} vídeos registrados, del {videos[0]['date']} al {videos[-1]['date']}\n")
    for video in videos[-5:]:
        applied, pending = len(video.get("applied", [])), len(video.get("pending", []))
        print(f"  {video['date']}  {video.get('topic', '')[:42]:<42} "
              f"{applied} ok / {pending} pendientes")

    stats = streaks(videos)
    insisting = sorted((s["run"], c) for c, s in stats.items() if s["run"] >= INSISTENCE_THRESHOLD)
    improving = [c for c, s in stats.items()
                 if s["run"] == 0 and s["applied"] and s["pending"]]

    if insisting:
        print(f"\nSe repite y no se aplica ({INSISTENCE_THRESHOLD}+ vídeos seguidos):")
        for run, check in reversed(insisting):
            print(f"  {run}x  {check} — {CHECKS[check]}")

    if improving:
        print("\nCorregido tras haberlo señalado:")
        for check in improving:
            print(f"  ok   {check} — {CHECKS[check]}")

    never = [c for c, s in stats.items() if not s["applied"] and not s["pending"]]
    if never:
        print(f"\nSin evaluar aún: {', '.join(never)}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")

    log = sub.add_parser("log", help="registra un vídeo y su evaluación")
    log.add_argument("--file", required=True, help="nombre del vídeo editado")
    log.add_argument("--topic", default="", help="de qué va, en pocas palabras")
    log.add_argument("--applied", default="", help="criterios cumplidos, separados por coma")
    log.add_argument("--pending", default="", help="criterios que fallan, separados por coma")
    log.add_argument("--note", default="", help="observación libre para este vídeo")

    sub.add_parser("checks", help="lista los criterios evaluables")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "checks":
        for check, description in CHECKS.items():
            print(f"  {check:22} {description}")
        return

    if args.command == "log":
        data = load()
        data["videos"].append({
            "date": date.today().isoformat(),
            "file": args.file,
            "topic": args.topic,
            "applied": split_ids(args.applied),
            "pending": split_ids(args.pending),
            "note": args.note,
        })
        save(data)
        print(f"registrado: {args.file}")
        print()

    report(load())


if __name__ == "__main__":
    main()
