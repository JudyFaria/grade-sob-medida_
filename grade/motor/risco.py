"""
Risco de nao conseguir a vaga.

Na versao anterior deste sistema isto era uma estimativa, porque se supunha
que 'vagas' fosse capacidade. Medindo a base real ficou claro que 'vagas' e
SALDO: mediana 3, maximo 56, e 965 turmas em zero. Capacidade nunca seria
zero. Isso troca um proxy por um dado observado.

O que se ganha:
  - turma com 0 vagas nao e 'disputada', e impossivel. Recomendar uma turma
    lotada e pior do que nao recomendar nada.
  - turma com 1 ou 2 vagas e um risco concreto, quantificavel.

O que NAO se ganha, e vale dizer com todas as letras:
  - nao da para calcular taxa de ocupacao, porque capacidade nao esta na base.
    Sabemos quantos lugares sobraram, nao quantos existiam.
  - o saldo e uma foto de um instante. Se o export foi tirado antes da
    matricula abrir, o numero significa capacidade inicial; se foi tirado no
    meio, significa sobra. A data do export precisa ser confirmada com a DSI,
    e ate la o sistema apresenta o numero como 'vagas no momento do export'.

A saturacao da faixa entra como sinal secundario, para diferenciar duas
turmas com o mesmo saldo: 5 vagas as 9h de terca valem menos que 5 vagas as
21h de sexta, porque a primeira faixa concentra muito mais oferta e procura.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .ingestao import Catalogo, Turma
from .mascara import FATIAS_POR_DIA, fatias_do_dia

# faixas de saldo -> rotulo e nivel (0 = tranquilo, 4 = impossivel)
FAIXAS = [
    (0, "sem vaga", 4),
    (2, "risco alto", 3),
    (5, "risco medio", 2),
    (15, "chance boa", 1),
    (10**9, "tranquilo", 0),
]


class Risco:
    def __init__(self, catalogo: Catalogo):
        self.catalogo = catalogo
        self.intencoes: Counter = Counter()
        self._saturacao = self._calcular_saturacao()

    # ---------- saturacao da faixa ----------

    def _calcular_saturacao(self) -> dict[tuple[int, int, int], float]:
        contagem: dict = defaultdict(int)
        for t in self.catalogo.turmas.values():
            for dia in range(6):
                bits = fatias_do_dia(t.mascara, dia)
                for f in range(FATIAS_POR_DIA):
                    if (bits >> f) & 1:
                        contagem[(t.periodo, dia, f)] += 1
        if not contagem:
            return {}
        por_periodo: dict[int, int] = defaultdict(int)
        for (per, _, _), v in contagem.items():
            por_periodo[per] = max(por_periodo[per], v)
        return {k: v / por_periodo[k[0]] for k, v in contagem.items()}

    def saturacao(self, turma: Turma) -> float:
        vals = []
        for dia in range(6):
            bits = fatias_do_dia(turma.mascara, dia)
            for f in range(FATIAS_POR_DIA):
                if (bits >> f) & 1:
                    vals.append(self._saturacao.get((turma.periodo, dia, f), 0.0))
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    # ---------- sinal vivo ----------

    def registrar_plano(self, periodo: int, turma_ids: list[str]) -> None:
        """Cada plano exportado e uma declaracao de intencao. E o unico jeito
        de saber a procura por uma turma que ainda tem saldo folgado."""
        for tid in turma_ids:
            self.intencoes[(periodo, tid)] += 1

    def intencao(self, turma: Turma) -> int:
        return self.intencoes.get(turma.chave, 0)

    # ---------- avaliacao ----------

    def nivel(self, turma: Turma) -> int:
        for limite, _, nivel in FAIXAS:
            if turma.vagas <= limite:
                base = nivel
                break
        else:
            base = 0
        if base in (1, 2) and self.saturacao(turma) > 0.6:
            base += 1          # mesmo saldo, faixa muito mais concorrida
        pedidos = self.intencao(turma)
        if pedidos and turma.vagas > 0 and pedidos >= turma.vagas:
            base = max(base, 3)   # ja tem mais gente pedindo do que sobra
        return min(base, 4)

    def rotulo(self, turma: Turma) -> str:
        return ["tranquilo", "chance boa", "risco medio", "risco alto", "sem vaga"][
            self.nivel(turma)
        ]

    def peso_sorteio(self, turma: Turma) -> float:
        """Peso da diversificacao: turma com folga tem mais chance de aparecer
        no topo entre alternativas equivalentes para o aluno."""
        if turma.lotada:
            return 0.0
        return 1.0 / (1.0 + 2.0 * self.nivel(turma))

    def descrever(self, turma: Turma) -> dict:
        return {
            "vagas": turma.vagas,
            "nivel": self.nivel(turma),
            "rotulo": self.rotulo(turma),
            "saturacao_faixa": self.saturacao(turma),
            "intencoes": self.intencao(turma),
            "lotada": turma.lotada,
        }

    # ---------- painel da coordenacao ----------

    def ranking(self, periodo: int, limite: int = 60) -> list[dict]:
        linhas = []
        for t in self.catalogo.turmas.values():
            if t.periodo != periodo:
                continue
            linhas.append({
                "turma_id": t.turma_id,
                "cod_disciplina": t.cod_disciplina,
                "nome": t.nome,
                "departamento": t.cod_departamento,
                "horario": t.horario_legivel(),
                "vagas": t.vagas,
                "nivel": self.nivel(t),
                "rotulo": self.rotulo(t),
                "saturacao_faixa": self.saturacao(t),
                "turmas_da_disciplina": len(self.catalogo.turmas_de(periodo, t.cod_disciplina)),
            })
        linhas.sort(key=lambda x: (-x["nivel"], x["vagas"], -x["saturacao_faixa"]))
        return linhas[:limite]

    def disciplinas_sem_saida(self, periodo: int) -> list[dict]:
        """Disciplinas em que TODAS as turmas estao lotadas. Quem precisa
        cursar agora nao tem para onde ir, e a coordenacao precisa saber."""
        saida = []
        for (per, cod), turmas in self.catalogo.por_disciplina.items():
            if per != periodo or not turmas:
                continue
            if all(t.lotada for t in turmas):
                saida.append({
                    "cod_disciplina": cod,
                    "nome": turmas[0].nome,
                    "departamento": turmas[0].cod_departamento,
                    "turmas": len(turmas),
                    "horarios": [t.horario_legivel() for t in turmas][:4],
                })
        saida.sort(key=lambda d: (-d["turmas"], d["nome"]))
        return saida
