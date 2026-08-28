"""
Explicacao de inviabilidade.

'Sem solucao' e a pior resposta possivel: devolve o aluno ao problema
original sem nenhuma informacao nova. O sistema tem de dizer quem esta
brigando com quem e o que acontece se ele ceder.

O subconjunto minimo culpado sai por delecao: partindo do conjunto inteiro,
testamos remover cada disciplina; o que sobra e um nucleo em que toda
disciplina e necessaria para a inviabilidade. E o mesmo raciocinio de nucleo
insatisfativel de um solver, feito na mao porque o conjunto e pequeno.
"""

from __future__ import annotations

from dataclasses import replace

from .enumerador import buscar, candidatas
from .ingestao import Catalogo
from .modelo import Preferencias
from .risco import Risco


def _viavel(catalogo: Catalogo, pref: Preferencias, sub: list[str]) -> bool:
    p = replace(pref, desejadas=list(sub), min_disciplinas=len(sub),
                obrigatorias=pref.obrigatorias & set(sub), creditos_min=0)
    return buscar(catalogo, p, None, limite=1).total > 0


def diagnosticar(catalogo: Catalogo, pref: Preferencias,
                 risco: Risco | None = None) -> dict:
    por_disciplina, _, cortes = candidatas(catalogo, pref)

    # caso 1: disciplina que ficou sem nenhuma turma utilizavel
    vazias = [c for c, v in por_disciplina.items() if not v]
    if vazias:
        motivos = []
        for cod in vazias:
            c = cortes[cod]
            if c["total"] == 0:
                razao = "nao tem turma ofertada neste periodo"
            elif c["lotadas"] == c["total"]:
                razao = f"todas as {c['total']} turmas estao sem vaga"
            elif c["bloqueadas"] and c["lotadas"]:
                razao = (f"das {c['total']} turmas, {c['lotadas']} estao sem vaga e "
                         f"{c['bloqueadas']} caem em horario que voce bloqueou")
            elif c["bloqueadas"]:
                razao = f"todas as {c['total']} turmas caem em horario que voce bloqueou"
            else:
                razao = "nenhuma turma sobrou depois dos filtros"
            motivos.append({"cod": cod, "nome": catalogo.nome(pref.periodo, cod),
                            "motivo": razao, "cortes": c})
        return {"viavel": False, "tipo": "sem_turma", "disciplinas": motivos}

    # caso 2: nucleo minimo de conflito de horario
    nucleo = list(pref.desejadas)
    for cod in list(nucleo):
        tentativa = [c for c in nucleo if c != cod]
        if tentativa and not _viavel(catalogo, pref, tentativa):
            nucleo = tentativa

    alternativas = []
    for cod in nucleo:
        resto = [c for c in pref.desejadas if c != cod]
        if not resto:
            continue
        p = replace(pref, desejadas=resto, min_disciplinas=len(resto),
                    obrigatorias=pref.obrigatorias & set(resto), creditos_min=0)
        r = buscar(catalogo, p, risco, limite=200)
        if r.total:
            alternativas.append({
                "remover": cod,
                "nome": catalogo.nome(pref.periodo, cod),
                "grades_liberadas": r.total,
                "creditos_restantes": r.grades[0].creditos,
            })
    alternativas.sort(key=lambda a: -a["grades_liberadas"])

    return {
        "viavel": False,
        "tipo": "conflito",
        "nucleo": [{"cod": c, "nome": catalogo.nome(pref.periodo, c),
                    "turmas": len(por_disciplina.get(c, []))} for c in nucleo],
        "pares": _pares_impossiveis(por_disciplina, nucleo, catalogo, pref.periodo),
        "alternativas": alternativas,
        "cortes": cortes,
    }


def _pares_impossiveis(por_disciplina, nucleo, catalogo, periodo) -> list[dict]:
    """Pares em que nenhuma combinacao de turmas fica sem choque. E a frase que
    o aluno precisa ler: 'X e Y so existem terca as 9h'."""
    pares = []
    for i, a in enumerate(nucleo):
        for b in nucleo[i + 1:]:
            ta, tb = por_disciplina.get(a, []), por_disciplina.get(b, [])
            if ta and tb and all(x.mascara & y.mascara for x in ta for y in tb):
                pares.append({
                    "a": a, "nome_a": catalogo.nome(periodo, a),
                    "b": b, "nome_b": catalogo.nome(periodo, b),
                })
    return pares
