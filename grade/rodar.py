#!/usr/bin/env python3
"""
Grade sob medida — ponto de entrada.

    python3 rodar.py

Sem dependencia externa: so a biblioteca padrao do Python 3.10+.
Por padrao le dados/turmas_horarios.csv e dados/disciplinas.csv.

    python3 rodar.py --turmas outro.csv --disciplinas outro2.csv --porta 8080
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from servidor.app import carregar, servir  # noqa: E402


def principal() -> int:
    p = argparse.ArgumentParser(description="Grade sob medida")
    p.add_argument("--turmas", default=RAIZ / "dados" / "turmas_horarios.csv")
    p.add_argument("--disciplinas", default=RAIZ / "dados" / "disciplinas.csv")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--sem-navegador", action="store_true")
    args = p.parse_args()

    turmas = Path(args.turmas)
    disciplinas = Path(args.disciplinas)

    if not turmas.exists():
        print(f"\n  Nao encontrei {turmas}")
        print("  Coloque seu turmas_horarios.csv na pasta dados/, ou aponte com --turmas.\n")
        return 1
    if not disciplinas.exists():
        print(f"  Aviso: {disciplinas} nao encontrado. Seguindo so com a oferta;")
        print("  nome e creditos virao de turmas_horarios.csv.")

    print(f"\n  Lendo {turmas.name} ...")
    t0 = time.perf_counter()
    try:
        carregar(turmas, disciplinas)
    except Exception as e:
        print(f"\n  Falhou ao ler os dados: {e}\n")
        return 1

    from servidor.app import ESTADO
    r = ESTADO["catalogo"].resumo()
    print(f"  Pronto em {time.perf_counter() - t0:.1f}s")
    mil = lambda n: f"{n:,}".replace(",", ".")
    print(f"    {mil(r['linhas_lidas'])} linhas -> {mil(r['linhas_unicas'])} blocos distintos")
    print(f"    {mil(r['turmas'])} turmas, {mil(r['disciplinas_ofertadas'])} disciplinas, "
          f"periodos {', '.join(str(x) for x in r['periodos'])}")
    if r["turmas_lotadas"]:
        print(f"    {r['turmas_lotadas']} turmas sem vaga")
    for aviso in r["avisos"]:
        print(f"    aviso: {aviso}")

    endereco = f"http://127.0.0.1:{args.porta}"
    try:
        servidor = servir(args.porta)
    except OSError as e:
        print(f"\n  Nao consegui abrir a porta {args.porta}: {e}")
        print(f"  Tente outra: python3 rodar.py --porta {args.porta + 1}\n")
        return 1

    print(f"\n  Abra {endereco}")
    print("  Ctrl+C para parar.\n")

    if not args.sem_navegador:
        threading.Timer(0.8, lambda: webbrowser.open(endereco)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  Encerrado.\n")
        servidor.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
