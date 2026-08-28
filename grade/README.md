# Grade sob medida

Aplicação local para montar grade horária a partir dos CSVs do SGU, e para
enxergar onde a oferta aperta.

Sem integração com nada e sem dependência externa: só a biblioteca padrão do
Python. Você aponta para seus arquivos e roda.

---

## Como rodar

Precisa de **Python 3.10 ou mais novo**. Nada além disso.

```bash
cd grade
python3 rodar.py
```

O navegador abre em `http://127.0.0.1:8000`. `Ctrl+C` encerra.

Por padrão o sistema lê `dados/turmas_horarios.csv` e `dados/disciplinas.csv`.
Para apontar para outro lugar:

```bash
python3 rodar.py --turmas /caminho/turmas.csv --disciplinas /caminho/disc.csv
python3 rodar.py --porta 8080
python3 rodar.py --sem-navegador
```

Trocar os dados de um período para o outro é substituir os dois CSVs e
reiniciar. Não há banco, não há migração, não há estado a limpar.

---

## Estrutura

```
grade/
  rodar.py              ponto de entrada
  dados/
    turmas_horarios.csv   ← seus arquivos
    disciplinas.csv
  motor/                  toda a lógica; não sabe que existe web
    mascara.py            semana como máscara de bits
    ingestao.py           leitura dos CSVs e limpeza
    modelo.py             preferências do aluno e grade
    pontuacao.py          aderência ao formato de dia
    enumerador.py         busca das grades viáveis
    pareto.py             seleção e diversificação
    inviabilidade.py      explicação de quando não fecha
    risco.py              risco de não conseguir a vaga
    panorama.py           contagens da oferta
    conflitos.py          grafo de conflito estrutural
  servidor/
    app.py                servidor HTTP e API JSON
  web/
    index.html  estilo.css  app.js
```

O `motor/` é independente do servidor. Dá para usar no Jupyter ou num script:

```python
from motor import Catalogo, Risco, Preferencias, FormatoDia, buscar

c = Catalogo("dados/turmas_horarios.csv", "dados/disciplinas.csv")
r = Risco(c)
pref = Preferencias(periodo=20261, desejadas=["PSI1500", "PSI1501"],
                    formato=FormatoDia(max_aulas_seguidas=2, intervalo_desejado_min=60))
print(buscar(c, pref, r).total)
```

---

## O que o sistema faz

**Montar grade.** O aluno diz o que quer cursar, quando não pode estar no
campus e como quer o ritmo do dia. O sistema devolve as grades viáveis,
descartando turmas sem vaga, e explica o que trava quando não fecha.

**Panorama da oferta.** Mapa de calor de ocupação por faixa de 30 min, taxa de
lotação por hora de início e por dia, quadro por departamento, e os conflitos
internos da própria base.

**Vagas e gargalos.** Disciplinas em que todas as turmas estão lotadas,
disciplinas de turma única, e ranking de turmas por risco de não conseguir a
vaga.

**Conflitos estruturais.** Pares de disciplinas em que nenhuma combinação de
turmas fica sem choque.

**Dados.** O que foi lido, o que foi descartado e por quê.

---

## O que foi encontrado nos seus arquivos

Quatro coisas quebram uma leitura ingênua da base. Todas estão tratadas no
código, e todas aparecem na aba **Dados**.

### 1. As linhas vêm duplicadas

74.381 linhas descrevem 10.212 blocos de aula distintos — fator 7,3x. O mesmo
bloco se repete de 2 a 19 vezes. Sem deduplicar, toda contagem sai inflada e a
grade desenha a mesma aula várias vezes sobreposta.

### 2. `vagas` é saldo, não capacidade

Este é o achado que mais muda o projeto. A mediana é 3, o máximo é 56, e 965
turmas estão em zero. Capacidade nunca seria zero e teria mediana perto de 30.

Então `vagas` é o número de lugares **ainda abertos**, e isso é uma boa
notícia: você já tem sinal de procura, e ele não precisa ser estimado. A taxa
de lotação por faixa confirma o diagnóstico de partida — 09:00 e 11:00 são as
faixas que mais lotam, contra 5,6% às 21:00.

Duas ressalvas honestas:

- **Não dá para calcular taxa de ocupação**, porque capacidade não está na
  base. Sabemos quantos lugares sobraram, não quantos existiam.
- **É uma foto de um instante.** Se o export foi tirado antes da matrícula
  abrir, o número significa capacidade inicial; se foi tirado no meio, é sobra.
  **Confirme a data do export com a DSI** — é o item de maior retorno e o mais
  fácil de conseguir.

O valor também oscila entre as linhas duplicadas da mesma turma (9, 9, 10, 9…)
sem tendência, em 4.705 das 4.947 turmas. Usamos a moda, que é robusta a esse
ruído.

### 3. O catálogo cobre pouco mais da metade da oferta

1.825 disciplinas aparecem na oferta, mas `disciplinas.csv` descreve 1.017 —
927 das ofertadas não têm ficha. Nome e créditos caem para o que vem em
`turmas_horarios.csv` quando falta a ficha.

### 4. Os dois arquivos codificam departamento de forma diferente

`disciplinas.csv` usa código numérico (731, 634); `turmas_horarios.csv` usa
sigla (COM, JUR). Os dois **não se juntam**. Vale a sigla da oferta.

### E dois números para a coordenação

**599 conflitos de sala e 321 de professor** já existem dentro da base: duas
turmas na mesma sala, dia e hora, ou um professor em dois lugares ao mesmo
tempo. Não é erro do sistema, é o que veio no arquivo. Isso significa que
restrição de sala e de professor precisa ser tratada como flexível em qualquer
reprogramação da oferta. Vale confirmar com a DSI se são exceções toleradas
pelo SGU ou ruído de extração.

**A taxa de estabilidade é 62,4%**: das 1.669 turmas presentes nos dois
períodos, 1.041 mantêm exatamente o mesmo horário. É a informação mais política
do pacote. Quanto mais alta, menos realista é propor reprogramar horários
existentes, e mais o caminho passa a ser abrir turma nova nas faixas com folga.

---

## Duas decisões de projeto que não são óbvias

**O risco de vaga não entra na fronteira de Pareto.** Se entrasse, a grade
equivalente porém mais concorrida seria eliminada por dominância — e ela é
justamente a alternativa que precisa sobrar para a procura se espalhar. Risco
não é preferência do aluno, é sinal de direção do sistema, e entra só como peso
no sorteio entre grades equivalentes.

**Cobertura vem antes de aderência.** Sem isso, largar disciplina vira
vantagem: uma grade com duas matérias sempre adere melhor ao formato do dia do
que uma com cinco, e o sistema passaria a recomendar cursar menos. As grades
menores continuam aparecendo, mas como alternativa, nunca no topo.

---

## Limites

O sistema **não reserva vaga** e não fala com o SGU. É uma ferramenta de
decisão; a matrícula continua onde sempre esteve.

**Não há pré-requisito nos dados.** Sem a estrutura curricular, o sistema não
sabe que adiar uma disciplina trava outras adiante. É o segundo pedido a fazer
à DSI.

As intenções registradas quando alguém copia um plano ficam em memória e se
perdem ao reiniciar. Persistir isso é o primeiro passo se virar serviço de
verdade.

Os números refletem o momento do export, não o estado de agora.
