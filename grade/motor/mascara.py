"""
Semana como mascara de bits.

A semana e discretizada em fatias de 30 minutos, das 07:00 as 23:00,
de Segunda a Sabado: 6 dias x 32 fatias = 192 bits. Cabe folgado num int
do Python, que nao tem limite de largura.

Testar choque entre duas turmas vira uma operacao de AND:

    if mascara_a & mascara_b:  # colidem

E o que permite enumerar dezenas de milhares de combinacoes em milissegundos
sem solver.
"""

from __future__ import annotations

DIAS = ("Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado")
INDICE_DIA = {d: i for i, d in enumerate(DIAS)}

# variantes de acentuacao que aparecem no export do SGU
INDICE_DIA.update(
    {
        "Terça": 1,
        "Sábado": 5,
        "SEGUNDA": 0,
        "TERCA": 1,
        "QUARTA": 2,
        "QUINTA": 3,
        "SEXTA": 4,
        "SABADO": 5,
    }
)

HORA_BASE = 7 * 60          # 07:00
FATIA = 30                  # minutos
FATIAS_POR_DIA = 32         # 07:00 -> 23:00
BITS_TOTAIS = len(DIAS) * FATIAS_POR_DIA


def para_minutos(hhmm: str) -> int:
    h, m = hhmm.strip().split(":")
    return int(h) * 60 + int(m)


def para_hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def indice_fatia(dia: str, hhmm: str) -> int:
    dia_idx = INDICE_DIA[dia.strip()]
    offset = (para_minutos(hhmm) - HORA_BASE) // FATIA
    return dia_idx * FATIAS_POR_DIA + offset


def mascara_bloco(dia: str, inicio: str, fim: str) -> int:
    """Bits acesos para um bloco de aula. Fim exclusivo: 13:00-15:00 nao
    colide com 15:00-17:00."""
    dia_idx = INDICE_DIA[dia.strip()]
    ini = (para_minutos(inicio) - HORA_BASE) // FATIA
    fim_i = (para_minutos(fim) - HORA_BASE) // FATIA
    ini = max(0, min(ini, FATIAS_POR_DIA))
    fim_i = max(0, min(fim_i, FATIAS_POR_DIA))
    if fim_i <= ini:
        return 0
    largura = fim_i - ini
    return ((1 << largura) - 1) << (dia_idx * FATIAS_POR_DIA + ini)


def mascara_janela(dias: list[str], inicio: str, fim: str) -> int:
    """Mascara de uma janela recorrente, usada para bloqueio (estagio, trabalho)."""
    m = 0
    for d in dias:
        m |= mascara_bloco(d, inicio, fim)
    return m


def fatias_do_dia(mascara: int, dia_idx: int) -> int:
    """Extrai os 32 bits de um dia como inteiro proprio."""
    return (mascara >> (dia_idx * FATIAS_POR_DIA)) & ((1 << FATIAS_POR_DIA) - 1)


def dias_ocupados(mascara: int) -> list[int]:
    return [i for i in range(len(DIAS)) if fatias_do_dia(mascara, i)]


def extremos_do_dia(bits_dia: int) -> tuple[int, int]:
    """(primeira fatia ocupada, ultima fatia ocupada + 1). (-1, -1) se vazio."""
    if not bits_dia:
        return (-1, -1)
    primeira = (bits_dia & -bits_dia).bit_length() - 1
    ultima = bits_dia.bit_length()
    return (primeira, ultima)


def lacunas_do_dia(bits_dia: int) -> list[tuple[int, int]]:
    """Janelas livres entre a primeira e a ultima aula, em fatias.
    Retorna lista de (inicio, fim) exclusivo."""
    primeira, ultima = extremos_do_dia(bits_dia)
    if primeira < 0:
        return []
    lacunas = []
    i = primeira
    while i < ultima:
        if not (bits_dia >> i) & 1:
            j = i
            while j < ultima and not (bits_dia >> j) & 1:
                j += 1
            lacunas.append((i, j))
            i = j
        else:
            i += 1
    return lacunas


def maior_sequencia_do_dia(bits_dia: int) -> int:
    """Maior corrida de fatias consecutivas ocupadas, em minutos."""
    melhor = atual = 0
    for i in range(FATIAS_POR_DIA):
        if (bits_dia >> i) & 1:
            atual += 1
            melhor = max(melhor, atual)
        else:
            atual = 0
    return melhor * FATIA


def minutos_ocupados(mascara: int) -> int:
    return bin(mascara).count("1") * FATIA
