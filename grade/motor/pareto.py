"""
Selecao das grades que vao para a tela.

FRONTEIRA DE PARETO
Nao existe grade otima unica: os criterios do aluno sao incomparaveis. Em vez
de inventar pesos, devolvemos so as grades nao dominadas e deixamos ele
escolher entre '3 dias no campus com 4h de janela' e '5 dias compactos'.

O risco de vaga NAO entra como eixo de dominancia, e isso e deliberado. Se
entrasse, a grade equivalente porem mais concorrida seria eliminada por ser
'pior' — e ela e justamente a alternativa que precisa sobrar para a demanda
se espalhar. Risco nao e preferencia do aluno, e sinal de direcao do sistema,
e entra so como peso de sorteio abaixo.

DIVERSIFICACAO PONDERADA
Se todo aluno receber a mesma sugestao no topo, criamos um congestionamento
novo. Entre grades que empatam dentro da margem de indiferenca do aluno,
sorteamos qual aparece primeiro, com peso inverso ao risco. O aluno nao perde
nada, porque as opcoes sao equivalentes para ele; o sistema ganha, porque a
procura se distribui. Funciona porque a sugestao e voluntaria: o espaco de
manobra e a indiferenca do aluno, nao autoridade sobre a matricula dele.
"""

from __future__ import annotations

import random

from .modelo import Grade
from .risco import Risco

MARGEM_INDIFERENCA = 0.75


def nao_dominadas(grades: list[Grade]) -> list[Grade]:
    """
    Criterios do aluno, todos 'menor e melhor'. A contagem de disciplinas
    atendidas entra NEGADA e em primeiro lugar por um motivo concreto: sem
    ela, largar disciplina vira vantagem. Uma grade com duas materias sempre
    adere melhor ao formato do dia do que uma com cinco, entao o sistema
    passaria a recomendar que o aluno cursasse menos — exatamente o oposto
    do que ele pediu ao listar as disciplinas.
    """

    def criterios(g: Grade):
        return (-float(g.atendidas), g.aderencia,
                float(g.dias_campus), float(g.minutos_lacuna))

    saida = []
    for a in grades:
        ca = criterios(a)
        if not any(
            a is not b
            and all(x <= y for x, y in zip(criterios(b), ca))
            and any(x < y for x, y in zip(criterios(b), ca))
            for b in grades
        ):
            saida.append(a)
    return saida


def diversificar(grades: list[Grade], risco: Risco | None, quantidade: int = 4,
                 semente: int | None = None, margem: float = MARGEM_INDIFERENCA):
    if not grades:
        return []
    ordenadas = sorted(grades, key=lambda g: (-g.atendidas, g.aderencia,
                                              g.dias_campus, g.risco))
    if risco is None:
        return ordenadas[:quantidade]

    rng = random.Random(semente)
    escolhidas: list[Grade] = []
    restantes = list(ordenadas)

    while restantes and len(escolhidas) < quantidade:
        # o empate so vale entre grades com a MESMA cobertura; uma grade que
        # cobre menos disciplinas nunca e 'equivalente' a uma que cobre mais
        cobertura = restantes[0].atendidas
        melhor = restantes[0].aderencia
        empatadas = [g for g in restantes
                     if g.atendidas == cobertura and g.aderencia <= melhor + margem]
        pesos = [1.0 / (1.0 + 2.0 * g.risco) for g in empatadas]
        pick = rng.choices(empatadas, weights=pesos, k=1)[0]
        escolhidas.append(pick)
        restantes = [g for g in restantes if g is not pick
                     and not _muito_parecida(g, escolhidas)]
    return escolhidas


def _muito_parecida(g: Grade, ja: list[Grade]) -> bool:
    """Duas grades que diferem em uma unica turma nao sao duas opcoes, sao uma."""
    conj = set(g.ids)
    return any(len(conj ^ set(o.ids)) <= 2 for o in ja)


def rotular(grades: list[Grade]) -> list[tuple[Grade, str]]:
    """Cada grade ganha um nome que diz para que ela serve. Rotulo generico
    obriga o aluno a comparar tudo de novo."""
    if not grades:
        return []

    # Cada rotulo procura o melhor entre as grades AINDA sem rotulo. Sem isso,
    # quando a mesma grade e a melhor em varios criterios os demais rotulos
    # degeneram em "alternativa equivalente" e o aluno perde a informacao de
    # para que serve cada opcao.
    criterios = [
        ("mais perto do que voce pediu", lambda g: (-g.atendidas, g.aderencia)),
        ("mais disciplinas atendidas", lambda g: -g.atendidas),
        ("menos dias no campus", lambda g: g.dias_campus),
        ("maior chance de conseguir a vaga", lambda g: -g.vagas_minimas),
        ("dia mais compacto", lambda g: g.minutos_lacuna),
    ]
    rot: dict[int, str] = {}
    for texto, chave in criterios:
        livres = [i for i in range(len(grades)) if i not in rot]
        if not livres:
            break
        rot[min(livres, key=lambda i: chave(grades[i]))] = texto
    return [(g, rot.get(i, "alternativa equivalente")) for i, g in enumerate(grades)]
