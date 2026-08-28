"""
Grafo de conflito estrutural entre disciplinas.

Duas disciplinas conflitam estruturalmente quando NENHUMA combinacao das
turmas delas fica sem choque de horario. O aluno que precisa das duas no
mesmo periodo simplesmente nao consegue, por mais que tente.

Custo: sao 1.825 disciplinas ofertadas, o que da cerca de 1,6 milhao de pares.
Comparar todos e caro e, pior, inutil: a maioria dos pares nunca seria cursada
junto. Por isso o calculo e restrito e ordenado:

  - so disciplinas com pelo menos uma turma com vaga
  - so pares dentro do mesmo departamento por padrao, que e onde mora a
    coincidencia de publico (ampliavel pela interface)
  - o resultado sai ordenado por quanto o par 'custa': disciplinas com poucas
    turmas e muita procura vem primeiro

Cada disciplina vira uma unica mascara-OR das suas turmas para uma triagem
rapida: se as mascaras-OR nem se tocam, nao ha conflito possivel e o par e
descartado sem comparar turma a turma.
"""

from __future__ import annotations

import time
from collections import defaultdict

from .ingestao import Catalogo


def _perfil(catalogo: Catalogo, periodo: int, apenas_com_vaga: bool):
    """Uma entrada por disciplina: turmas utilizaveis e a uniao das mascaras."""
    perfil = {}
    for (per, cod), turmas in catalogo.por_disciplina.items():
        if per != periodo:
            continue
        uteis = [t for t in turmas if t.mascara and (not apenas_com_vaga or not t.lotada)]
        if not uteis:
            continue
        uniao = 0
        for t in uteis:
            uniao |= t.mascara
        perfil[cod] = {
            "nome": uteis[0].nome,
            "departamento": uteis[0].cod_departamento,
            "turmas": uteis,
            "uniao": uniao,
            "n": len(uteis),
        }
    return perfil


def pares_impossiveis(catalogo: Catalogo, periodo: int, *,
                      mesmo_departamento: bool = True,
                      apenas_com_vaga: bool = True,
                      departamento: str | None = None,
                      limite: int = 200,
                      limite_ms: int = 8000) -> dict:
    t0 = time.perf_counter()
    perfil = _perfil(catalogo, periodo, apenas_com_vaga)

    if departamento:
        perfil = {k: v for k, v in perfil.items() if v["departamento"] == departamento}

    grupos: dict[str, list[str]] = defaultdict(list)
    if mesmo_departamento:
        for cod, p in perfil.items():
            grupos[p["departamento"]].append(cod)
    else:
        grupos["(todos)"] = list(perfil)

    achados = []
    comparados = 0
    truncado = False

    for _, codigos in grupos.items():
        codigos.sort()
        for i in range(len(codigos)):
            if (time.perf_counter() - t0) * 1000 > limite_ms:
                truncado = True
                break
            a = perfil[codigos[i]]
            for j in range(i + 1, len(codigos)):
                b = perfil[codigos[j]]
                comparados += 1
                # triagem barata: se as unioes nem se cruzam, nao ha conflito
                if not (a["uniao"] & b["uniao"]):
                    continue
                if any(not (x.mascara & y.mascara) for x in a["turmas"] for y in b["turmas"]):
                    continue
                achados.append({
                    "a": codigos[i], "nome_a": a["nome"], "turmas_a": a["n"],
                    "b": codigos[j], "nome_b": b["nome"], "turmas_b": b["n"],
                    "departamento": a["departamento"],
                    "custo": 1 / (a["n"] * b["n"]),
                })
        if truncado:
            break

    achados.sort(key=lambda p: (-p["custo"], p["nome_a"]))
    return {
        "periodo": periodo,
        "disciplinas_avaliadas": len(perfil),
        "pares_comparados": comparados,
        "pares_impossiveis": len(achados),
        "truncado": truncado,
        "ms": round((time.perf_counter() - t0) * 1000, 1),
        "escopo": ("mesmo departamento" if mesmo_departamento else "todos os pares")
                  + (" (so turmas com vaga)" if apenas_com_vaga else ""),
        "resultados": achados[:limite],
    }


def vizinhos(catalogo: Catalogo, periodo: int, cod: str,
             apenas_com_vaga: bool = True, limite: int = 60) -> dict:
    """
    Com quais disciplinas ESTA aqui nao combina.

    E a consulta que o aluno e o coordenador realmente fazem. Barata, porque
    compara uma disciplina contra as demais em vez de todas contra todas.
    """
    perfil = _perfil(catalogo, periodo, apenas_com_vaga)
    alvo = perfil.get(cod)
    if not alvo:
        return {"encontrada": False, "cod_disciplina": cod}

    choques = []
    for outro, p in perfil.items():
        if outro == cod:
            continue
        if not (alvo["uniao"] & p["uniao"]):
            continue
        if any(not (x.mascara & y.mascara) for x in alvo["turmas"] for y in p["turmas"]):
            continue
        choques.append({
            "cod_disciplina": outro, "nome": p["nome"],
            "departamento": p["departamento"], "turmas": p["n"],
        })
    choques.sort(key=lambda c: (c["turmas"], c["nome"]))
    return {
        "encontrada": True,
        "cod_disciplina": cod,
        "nome": alvo["nome"],
        "turmas": alvo["n"],
        "departamento": alvo["departamento"],
        "total_incompativeis": len(choques),
        "avaliadas": len(perfil),
        "incompativeis": choques[:limite],
    }
