"""
Enumeracao das grades viaveis para um aluno.

Para um aluno o problema e pequeno: 5 a 8 disciplinas com poucas turmas cada.
A poda por mascara de bits derruba o espaco de busca para alguns milhares de
combinacoes, e roda em milissegundos. Solver so passaria a valer no problema
de reprogramar a oferta inteira, que e outro produto.

Tres decisoes fazem a diferenca:

  - turma lotada nao entra por padrao. Sugerir uma turma com zero vagas e
    pior do que nao sugerir nada.
  - as disciplinas sao ordenadas da mais restrita para a menos restrita, para
    a de turma unica travar cedo e virar o esqueleto da grade.
  - a poda acontece antes de descer, assim que a mascara parcial colide.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .ingestao import Catalogo, Turma
from .mascara import mascara_janela
from .modelo import Grade, Preferencias
from .pontuacao import avaliar
from .risco import Risco

LIMITE_SOLUCOES = 5000
LIMITE_MS = 2000


@dataclass
class Resultado:
    grades: list[Grade]
    total: int
    truncado: bool
    ms: float
    turmas_por_disciplina: dict[str, int]
    cortes: dict[str, dict]


def mascara_bloqueios(pref: Preferencias) -> int:
    m = 0
    for b in pref.bloqueios:
        m |= mascara_janela(b.dias, b.hora_inicio, b.hora_fim)
    return m


def candidatas(catalogo: Catalogo, pref: Preferencias):
    """Aplica as restricoes duras antes de enumerar e registra por que cada
    turma caiu, para a tela de inviabilidade poder explicar."""
    bloqueio = mascara_bloqueios(pref)
    por_disciplina: dict[str, list[Turma]] = {}
    cortes: dict[str, dict] = {}

    for cod in pref.desejadas:
        opcoes, lotadas, bloqueadas, evitadas = [], 0, 0, 0
        for t in catalogo.turmas_de(pref.periodo, cod):
            if not t.mascara:
                continue
            if t.turma_id in pref.evitar_turmas:
                evitadas += 1
                continue
            if t.lotada and not pref.incluir_lotadas:
                lotadas += 1
                continue
            if t.mascara & bloqueio:
                bloqueadas += 1
                continue
            opcoes.append(t)
        por_disciplina[cod] = opcoes
        cortes[cod] = {
            "total": len(catalogo.turmas_de(pref.periodo, cod)),
            "sobraram": len(opcoes),
            "lotadas": lotadas,
            "bloqueadas": bloqueadas,
            "evitadas": evitadas,
        }
    return por_disciplina, bloqueio, cortes


def buscar(catalogo: Catalogo, pref: Preferencias, risco: Risco | None = None,
           limite: int = LIMITE_SOLUCOES) -> Resultado:
    t0 = time.perf_counter()
    por_disciplina, _, cortes = candidatas(catalogo, pref)

    minimo = (pref.min_disciplinas if pref.min_disciplinas is not None
              else len(pref.desejadas))
    ordem = sorted(pref.desejadas, key=lambda c: len(por_disciplina.get(c, [])))

    solucoes: list[list[Turma]] = []
    truncado = False

    def descer(i, escolhidas, mascara, creditos):
        nonlocal truncado
        if truncado:
            return
        if len(solucoes) >= limite or (time.perf_counter() - t0) * 1000 > LIMITE_MS:
            truncado = True
            return
        restam = len(ordem) - i
        if len(escolhidas) + restam < minimo:
            return
        if i == len(ordem):
            if len(escolhidas) >= minimo and pref.creditos_min <= creditos <= pref.creditos_max:
                solucoes.append(list(escolhidas))
            return

        cod = ordem[i]
        for t in por_disciplina.get(cod, []):
            if t.mascara & mascara:
                continue
            if creditos + t.creditos > pref.creditos_max:
                continue
            escolhidas.append(t)
            descer(i + 1, escolhidas, mascara | t.mascara, creditos + t.creditos)
            escolhidas.pop()

        if cod not in pref.obrigatorias and len(escolhidas) + restam - 1 >= minimo:
            descer(i + 1, escolhidas, mascara, creditos)

    descer(0, [], 0, 0)

    grades = [_montar(s, pref, risco) for s in solucoes]
    return Resultado(
        grades=grades, total=len(grades), truncado=truncado,
        ms=round((time.perf_counter() - t0) * 1000, 2),
        turmas_por_disciplina={c: len(v) for c, v in por_disciplina.items()},
        cortes=cortes,
    )


def _montar(turmas: list[Turma], pref: Preferencias, risco: Risco | None) -> Grade:
    mascara = 0
    creditos = 0
    for t in turmas:
        mascara |= t.mascara
        creditos += t.creditos

    aval = avaliar(mascara, pref.formato)

    if risco and turmas:
        niveis = [risco.nivel(t) for t in turmas]
        media, pior = sum(niveis) / len(niveis), max(niveis)
    else:
        media, pior = 0.0, 0

    return Grade(
        turmas=list(turmas), mascara=mascara, creditos=creditos,
        dias_campus=aval["dias_campus"], minutos_lacuna=aval["minutos_lacuna"],
        aderencia=aval["nota"], risco=round(media, 3), pior_risco=pior,
        atendidas=len(turmas), detalhes={"avaliacao": aval},
    )
