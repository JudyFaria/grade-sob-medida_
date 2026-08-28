"""Preferencias do aluno e a grade resultante."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ingestao import Turma
from .mascara import DIAS


@dataclass
class Bloqueio:
    """Janela indisponivel. Restricao dura: filtra turmas, nao pontua."""
    rotulo: str
    dias: list[str]
    hora_inicio: str
    hora_fim: str


@dataclass
class FormatoDia:
    """
    O ritmo de dia desejado.

    Nao confundir com 'minimizar janela'. Um aluno pode QUERER intervalo:
    'duas aulas de manha, um intervalo, mais uma ou duas' e exatamente
    max_aulas_seguidas=2 com intervalo_desejado_min=60.
    """
    inicio_mais_cedo: str = "07:00"
    fim_mais_tarde: str = "23:00"
    max_aulas_seguidas: int = 3        # em blocos de 2h
    intervalo_desejado_min: int = 0    # minutos; 0 = tanto faz
    intervalo_tolerado_max: int = 240
    max_dias_campus: int = 6


@dataclass
class Preferencias:
    periodo: int
    desejadas: list[str]
    obrigatorias: set[str] = field(default_factory=set)
    bloqueios: list[Bloqueio] = field(default_factory=list)
    formato: FormatoDia = field(default_factory=FormatoDia)
    creditos_min: int = 0
    creditos_max: int = 99
    min_disciplinas: int | None = None
    evitar_turmas: set[str] = field(default_factory=set)
    incluir_lotadas: bool = False      # por padrao turma sem vaga nem entra


@dataclass
class Grade:
    turmas: list[Turma]
    mascara: int
    creditos: int
    dias_campus: int
    minutos_lacuna: int
    aderencia: float                   # 0 = formato perfeito
    risco: float                       # 0..4, media do nivel das turmas
    pior_risco: int
    atendidas: int = 0                 # quantas disciplinas pedidas entraram
    detalhes: dict = field(default_factory=dict)

    @property
    def ids(self) -> list[str]:
        return [t.turma_id for t in self.turmas]

    @property
    def vagas_minimas(self) -> int:
        return min((t.vagas for t in self.turmas), default=0)

    def agenda(self) -> dict[str, list[dict]]:
        por_dia: dict[str, list[dict]] = {d: [] for d in DIAS}
        for t in self.turmas:
            for b in t.blocos:
                por_dia.setdefault(b.dia, []).append({
                    "turma_id": t.turma_id,
                    "cod_disciplina": t.cod_disciplina,
                    "nome": t.nome,
                    "dia_idx": b.dia_idx,
                    "inicio": b.hora_inicio,
                    "fim": b.hora_fim,
                    "sala_id": b.sala_id,
                    "vagas": t.vagas,
                })
        for d in por_dia:
            por_dia[d].sort(key=lambda x: x["inicio"])
        return por_dia
