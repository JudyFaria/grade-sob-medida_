"""
Aderencia ao formato de dia.

A funcao objetivo padrao em montagem de grade e 'minimizar janela'. Ela esta
errada para boa parte dos alunos. Quem pede 'duas aulas de manha, um intervalo,
mais uma ou duas' quer justamente uma janela, de tamanho especifico, no meio
do dia. Aqui a nota nao mede buraco: mede distancia ate o formato pedido.

Nota 0 = o dia saiu exatamente como o aluno desenhou. Quanto maior, pior.
"""

from __future__ import annotations

from .mascara import (
    FATIA,
    FATIAS_POR_DIA,
    HORA_BASE,
    extremos_do_dia,
    fatias_do_dia,
    lacunas_do_dia,
    maior_sequencia_do_dia,
    para_minutos,
)
from .modelo import FormatoDia

MINUTOS_POR_AULA = 120  # bloco padrao


def avaliar(mascara: int, formato: FormatoDia) -> dict:
    """Decompoe a nota em componentes nomeados, para a interface poder
    explicar por que uma grade ficou em segundo lugar."""
    limite_cedo = (para_minutos(formato.inicio_mais_cedo) - HORA_BASE) // FATIA
    limite_tarde = (para_minutos(formato.fim_mais_tarde) - HORA_BASE) // FATIA

    pen_cedo = pen_tarde = 0.0
    pen_sequencia = 0.0
    pen_intervalo = 0.0
    minutos_lacuna = 0
    dias = 0
    detalhe_dias: list[dict] = []

    for dia_idx in range(6):
        bits = fatias_do_dia(mascara, dia_idx)
        if not bits:
            continue
        dias += 1
        primeira, ultima = extremos_do_dia(bits)

        if primeira < limite_cedo:
            pen_cedo += (limite_cedo - primeira) * FATIA / 60.0
        if ultima > limite_tarde:
            pen_tarde += (ultima - limite_tarde) * FATIA / 60.0

        seq = maior_sequencia_do_dia(bits)
        max_seq = formato.max_aulas_seguidas * MINUTOS_POR_AULA
        if seq > max_seq:
            pen_sequencia += (seq - max_seq) / 60.0

        lacunas = lacunas_do_dia(bits)
        total_lacuna = sum((f - i) * FATIA for i, f in lacunas)
        minutos_lacuna += total_lacuna

        if formato.intervalo_desejado_min > 0:
            # o aluno quer intervalo: um dia sem nenhum e desvio, e um
            # intervalo curto demais tambem
            maior_lacuna = max(((f - i) * FATIA for i, f in lacunas), default=0)
            faltou = formato.intervalo_desejado_min - maior_lacuna
            if faltou > 0 and seq > MINUTOS_POR_AULA:
                pen_intervalo += faltou / 60.0

        excesso = total_lacuna - formato.intervalo_tolerado_max
        if excesso > 0:
            pen_intervalo += excesso / 60.0

        detalhe_dias.append(
            {
                "dia": dia_idx,
                "inicio": _hora(primeira),
                "fim": _hora(ultima),
                "lacuna_min": total_lacuna,
                "maior_sequencia_min": seq,
            }
        )

    pen_dias = max(0, dias - formato.max_dias_campus) * 2.0

    nota = (
        1.6 * pen_cedo
        + 1.0 * pen_tarde
        + 1.2 * pen_sequencia
        + 1.4 * pen_intervalo
        + 1.0 * pen_dias
    )

    return {
        "nota": round(nota, 3),
        "dias_campus": dias,
        "minutos_lacuna": minutos_lacuna,
        "componentes": {
            "cedo_demais": round(pen_cedo, 2),
            "tarde_demais": round(pen_tarde, 2),
            "aulas_seguidas_demais": round(pen_sequencia, 2),
            "intervalo_fora_do_pedido": round(pen_intervalo, 2),
            "dias_a_mais": round(pen_dias, 2),
        },
        "dias": detalhe_dias,
    }


def explicar(avaliacao: dict) -> list[str]:
    """Frases curtas para a interface. So o que de fato pesou."""
    c = avaliacao["componentes"]
    frases = []
    if c["cedo_demais"] > 0.1:
        frases.append("comeca antes do horario que voce pediu")
    if c["tarde_demais"] > 0.1:
        frases.append("termina depois do horario que voce pediu")
    if c["aulas_seguidas_demais"] > 0.1:
        frases.append("tem mais aulas seguidas do que voce queria")
    if c["intervalo_fora_do_pedido"] > 0.1:
        frases.append("o intervalo nao ficou do tamanho que voce pediu")
    if c["dias_a_mais"] > 0.1:
        frases.append("usa mais dias de campus do que voce queria")
    if not frases:
        frases.append("bate com o formato que voce desenhou")
    return frases


def _hora(fatia: int) -> str:
    total = HORA_BASE + fatia * FATIA
    return f"{total // 60:02d}:{total % 60:02d}"
