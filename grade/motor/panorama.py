"""
Panorama da oferta: as contagens que a coordenacao precisa ver antes de
qualquer otimizacao.

Nada aqui e otimizacao. Sao contagens e cruzamentos que ja respondem
perguntas concretas, e que na base real confirmam o diagnostico de partida:
a oferta se concentra em poucas faixas, e e nelas que a lotacao acontece.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .ingestao import Catalogo
from .mascara import DIAS, FATIA, FATIAS_POR_DIA, HORA_BASE, fatias_do_dia, para_hhmm


def mapa_de_calor(catalogo: Catalogo, periodo: int) -> dict:
    """
    Ocupacao por dia e faixa de 30 min. Duas camadas:
      - blocos: quantas turmas ocupam aquela fatia
      - lotadas: quantas delas estao sem vaga
    A razao entre as duas e a taxa de lotacao da faixa, que e o numero que
    interessa: nao basta saber onde tem muita aula, precisa saber onde a aula
    que existe nao da conta.
    """
    blocos = [[0] * FATIAS_POR_DIA for _ in range(6)]
    lotadas = [[0] * FATIAS_POR_DIA for _ in range(6)]
    vagas = [[0] * FATIAS_POR_DIA for _ in range(6)]

    for t in catalogo.turmas.values():
        if t.periodo != periodo:
            continue
        for dia in range(6):
            bits = fatias_do_dia(t.mascara, dia)
            for f in range(FATIAS_POR_DIA):
                if (bits >> f) & 1:
                    blocos[dia][f] += 1
                    vagas[dia][f] += t.vagas
                    if t.lotada:
                        lotadas[dia][f] += 1

    pico = max((max(l) for l in blocos), default=0)
    return {
        "dias": list(DIAS),
        "fatias": [para_hhmm(HORA_BASE + f * FATIA) for f in range(FATIAS_POR_DIA)],
        "blocos": blocos,
        "lotadas": lotadas,
        "vagas": vagas,
        "pico": pico,
    }


def por_hora_inicio(catalogo: Catalogo, periodo: int) -> list[dict]:
    """Taxa de lotacao por hora de inicio. E o corte que mostra que 9h e 11h
    nao sao so as faixas mais cheias, sao as que mais lotam."""
    tot: Counter = Counter()
    lot: Counter = Counter()
    for t in catalogo.turmas.values():
        if t.periodo != periodo or not t.blocos:
            continue
        h = min(b.hora_inicio for b in t.blocos)
        tot[h] += 1
        if t.lotada:
            lot[h] += 1
    saida = [{"hora": h, "turmas": n, "lotadas": lot[h],
              "taxa_lotacao": round(100 * lot[h] / n, 1)}
             for h, n in tot.items() if n >= 10]
    saida.sort(key=lambda x: x["hora"])
    return saida


def por_dia(catalogo: Catalogo, periodo: int) -> list[dict]:
    tot = [0] * 6
    lot = [0] * 6
    for t in catalogo.turmas.values():
        if t.periodo != periodo:
            continue
        dias = {b.dia_idx for b in t.blocos}
        for d in dias:
            tot[d] += 1
            if t.lotada:
                lot[d] += 1
    return [{"dia": DIAS[d], "turmas": tot[d], "lotadas": lot[d]} for d in range(6)]


def por_departamento(catalogo: Catalogo, periodo: int, limite: int = 20) -> list[dict]:
    agrupado: dict[str, dict] = defaultdict(
        lambda: {"turmas": 0, "lotadas": 0, "vagas": 0, "disciplinas": set()}
    )
    for t in catalogo.turmas.values():
        if t.periodo != periodo:
            continue
        d = agrupado[t.cod_departamento or "(sem depto)"]
        d["turmas"] += 1
        d["vagas"] += t.vagas
        d["disciplinas"].add(t.cod_disciplina)
        if t.lotada:
            d["lotadas"] += 1
    saida = [{"departamento": k, "turmas": v["turmas"], "lotadas": v["lotadas"],
              "vagas": v["vagas"], "disciplinas": len(v["disciplinas"]),
              "taxa_lotacao": round(100 * v["lotadas"] / v["turmas"], 1)}
             for k, v in agrupado.items()]
    saida.sort(key=lambda x: -x["turmas"])
    return saida[:limite]


def gargalos(catalogo: Catalogo, periodo: int, limite: int = 40) -> list[dict]:
    """
    Disciplina de turma unica e restricao rigida para quem precisa se formar.
    Cruzada com lotacao e com a saturacao da faixa, ela vira a lista curta de
    gargalos sistemicos: se a unica turma esta lotada e esta no horario mais
    concorrido, aquela disciplina trava o curso inteiro.
    """
    saida = []
    for (per, cod), turmas in catalogo.por_disciplina.items():
        if per != periodo or len(turmas) != 1:
            continue
        t = turmas[0]
        saida.append({
            "cod_disciplina": cod,
            "nome": t.nome,
            "departamento": t.cod_departamento,
            "turma_id": t.turma_id,
            "horario": t.horario_legivel(),
            "vagas": t.vagas,
            "lotada": t.lotada,
            "creditos": t.creditos,
        })
    saida.sort(key=lambda d: (not d["lotada"], d["vagas"], d["nome"]))
    return saida[:limite]


def salas(catalogo: Catalogo, periodo: int) -> dict:
    """Ocupacao de sala. A folga aqui e o espaco para onde uma eventual
    reprogramacao da oferta poderia empurrar turma."""
    uso: dict[str, int] = Counter()
    conflitos: dict[tuple, list[str]] = defaultdict(list)
    for t in catalogo.turmas.values():
        if t.periodo != periodo:
            continue
        for b in t.blocos:
            if not b.sala_id:
                continue
            uso[b.sala_id] += b.minutos
            conflitos[(b.dia, b.hora_inicio, b.sala_id)].append(t.turma_id)

    duplas = [{"dia": k[0], "hora": k[1], "sala": k[2], "turmas": sorted(set(v))}
              for k, v in conflitos.items() if len(set(v)) > 1]
    duplas.sort(key=lambda x: -len(x["turmas"]))
    return {
        "salas_distintas": len(uso),
        "minutos_totais": sum(uso.values()),
        "mais_usadas": [{"sala": s, "horas_semana": round(m / 60, 1)}
                        for s, m in uso.most_common(12)],
        "conflitos_de_sala": duplas[:40],
        "total_conflitos_de_sala": len(duplas),
    }


def professores(catalogo: Catalogo, periodo: int) -> dict:
    """Carga e conflito de professor. Atencao: as linhas sem horario (TCC,
    orientacao, estagio) nao entram, entao a carga aqui e subestimada."""
    carga: Counter = Counter()
    conflitos: dict[tuple, list[str]] = defaultdict(list)
    for t in catalogo.turmas.values():
        if t.periodo != periodo:
            continue
        for p in t.professores:
            carga[p] += t.minutos_semana
            for b in t.blocos:
                conflitos[(b.dia, b.hora_inicio, p)].append(t.turma_id)

    duplas = [{"dia": k[0], "hora": k[1], "professor": k[2], "turmas": sorted(set(v))}
              for k, v in conflitos.items() if len(set(v)) > 1]
    duplas.sort(key=lambda x: -len(x["turmas"]))
    return {
        "professores_distintos": len(carga),
        "carga_media_horas": round(sum(carga.values()) / 60 / max(len(carga), 1), 1),
        "conflitos_de_professor": duplas[:40],
        "total_conflitos_de_professor": len(duplas),
    }


def estabilidade(catalogo: Catalogo) -> dict:
    """
    Quantas turmas mantem exatamente o mesmo horario entre os dois periodos.

    E a informacao mais politica do pacote: se a maior parte da oferta esta
    congelada por tradicao, reprogramar horario e inviavel na pratica, e o
    caminho passa a ser abrir turma nova em vez de mover turma existente.
    """
    if len(catalogo.periodos) < 2:
        return {"aplicavel": False}
    a, b = catalogo.periodos[-2], catalogo.periodos[-1]
    ids_a = {t.turma_id: t for t in catalogo.turmas.values() if t.periodo == a}
    ids_b = {t.turma_id: t for t in catalogo.turmas.values() if t.periodo == b}
    comuns = set(ids_a) & set(ids_b)
    iguais = sum(1 for i in comuns if ids_a[i].mascara == ids_b[i].mascara)
    return {
        "aplicavel": True,
        "periodo_a": a, "periodo_b": b,
        "turmas_a": len(ids_a), "turmas_b": len(ids_b),
        "turmas_em_ambos": len(comuns),
        "mesmo_horario": iguais,
        "taxa_estabilidade": round(100 * iguais / len(comuns), 1) if comuns else 0.0,
        "so_em_a": len(set(ids_a) - set(ids_b)),
        "so_em_b": len(set(ids_b) - set(ids_a)),
    }
