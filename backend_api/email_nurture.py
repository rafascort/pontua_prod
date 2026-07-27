# /opt/pontua/AutoPonto/backend_api/email_nurture.py
"""
Repertórios de nutrição — Sistema Ponto

Só texto, sem lógica: é aqui que você edita as mensagens.

Quatro repertórios, um por estado do cliente. O sistema usa em rodízio:
manda o próximo ainda não usado e, quando acaba, recomeça — a essa
altura já se passaram meses.

Formato de cada item:
  assunto     linha de assunto do e-mail
  subtitulo   texto pequeno abaixo de "Sistema Ponto" no cabeçalho
  titulo      título grande dentro do e-mail
  paragrafos  lista de textos. O primeiro sai em destaque.
              *texto entre asteriscos* fica azul e em negrito.
              {restantes} e {usadas} são trocados pelo saldo real.
  cta         (texto do botão, destino)  destino: 'app' ou 'planos'
  rodape      linha pequena e centralizada abaixo do botão (opcional)
  planos      True para incluir a tabela de preços
  saldo       True para incluir a barra de páginas usadas
"""

POOLS = {

    # ══════════════════════════════════════════════════════════════
    # A · NUNCA USOU — cadastrou e não processou nada
    # ══════════════════════════════════════════════════════════════
    'A': [
        {
            'assunto': 'Posso te ajudar a começar?',
            'subtitulo': 'Estamos aqui para ajudar',
            'titulo': 'Vi que você ainda não testou',
            'paragrafos': [
                'Criar a conta foi o primeiro passo. O segundo leva menos de '
                '2 minutos: envie um cartão de ponto ou holerite em PDF e '
                'receba a planilha pronta.',
                'Travou em algo — formato do arquivo, upload, períodos? '
                '*Responda este e-mail* que eu te ajudo pessoalmente.',
            ],
            'cta': ('Testar agora', 'app'),
        },
        {
            'assunto': 'Funciona com qualquer layout de cartão de ponto',
            'subtitulo': 'Sem configuração',
            'titulo': 'DATASUL, Control iD, cartão manual — a IA lê todos',
            'paragrafos': [
                'Você não precisa informar o formato nem configurar nada. '
                'A IA *interpreta o documento visualmente*, como uma pessoa '
                'faria — inclusive scans tortos e cartões preenchidos à mão.',
                'É por isso que funciona com layouts que a gente nunca viu antes.',
            ],
            'cta': ('Testar com meu PDF', 'app'),
            'rodape': 'Suas 50 páginas grátis continuam disponíveis.',
        },
        {
            'assunto': 'De PDF para planilha em 2 minutos',
            'subtitulo': 'Como funciona',
            'titulo': 'São três passos, só isso',
            'paragrafos': [
                '*1. Envie o PDF* — cartão de ponto ou holerite, de qualquer layout.',
                '*2. Confirme o que a IA detectou* — os períodos aparecem na tela '
                'para você revisar antes de processar.',
                '*3. Baixe a planilha* — CSV com o calendário completo, ou Excel '
                'com uma aba por funcionário.',
            ],
            'cta': ('Fazer meu primeiro teste', 'app'),
        },
        {
            'assunto': 'Como peritos usam o Sistema Ponto',
            'subtitulo': 'Caso de uso',
            'titulo': 'Os cartões de um processo inteiro, em uma planilha',
            'paragrafos': [
                'Anexe todos os cartões de ponto do período e receba um '
                '*CSV cronológico completo* — com o calendário fechado, dia a dia, '
                'incluindo as folgas e os dias sem marcação.',
                'O formato sai pronto para conferência e para alimentar o cálculo. '
                'O que levava uma tarde de digitação sai em minutos.',
            ],
            'cta': ('Testar com um processo', 'app'),
        },
        {
            'assunto': 'E os holerites? Também dá',
            'subtitulo': 'Não é só cartão de ponto',
            'titulo': 'Contracheques viram Excel também',
            'paragrafos': [
                'A IA lê os holerites, lista *todas as verbas encontradas* — '
                'salário, horas extras, INSS, FGTS, adicionais — e você escolhe '
                'quais quer na planilha.',
                'O resultado é um Excel com uma aba por funcionário e as colunas '
                'organizadas por verba, indexadas por mês.',
            ],
            'cta': ('Testar com holerites', 'app'),
        },
        {
            'assunto': 'Suas 50 páginas grátis continuam aqui',
            'subtitulo': 'Seu saldo não expira',
            'titulo': 'Ainda dá tempo de testar',
            'paragrafos': [
                'Você tem *{restantes} páginas grátis* na sua conta. Elas não '
                'expiram e não têm prazo — ficam esperando o dia em que você '
                'precisar.',
                'Se aparecer um cartão de ponto ou holerite para converter, '
                'é só entrar e usar.',
            ],
            'cta': ('Usar minhas páginas', 'app'),
        },
    ],

    # ══════════════════════════════════════════════════════════════
    # B · USOU PARTE — testou e parou, ainda tem saldo
    # ══════════════════════════════════════════════════════════════
    'B': [
        {
            'assunto': 'Sobraram {restantes} páginas do seu teste',
            'subtitulo': 'Seu saldo continua disponível',
            'titulo': 'Você ainda tem {restantes} páginas',
            'paragrafos': [
                'Você chegou a processar {usadas} páginas e parou. O saldo '
                '*não expira* — está lá quando precisar.',
                'Se tiver um novo lote de cartões ou holerites, é só continuar '
                'de onde parou.',
            ],
            'cta': ('Usar meu saldo', 'app'),
            'saldo': True,
        },
        {
            'assunto': 'Turnos noturnos agora saem certos',
            'subtitulo': 'Melhorias no sistema',
            'titulo': 'Melhoramos o que mais dava trabalho',
            'paragrafos': [
                'Jornada que começa num dia e termina no outro sempre foi o '
                'ponto mais difícil de ler automaticamente. O *pareamento de '
                'turnos noturnos* foi refeito e agora acerta esses casos.',
                'Se você teve trabalho com isso antes, vale testar de novo — '
                'seu saldo de {restantes} páginas continua aí.',
            ],
            'cta': ('Testar de novo', 'app'),
        },
        {
            'assunto': 'Um lote de 300 páginas sai quase no mesmo tempo que um de 50',
            'subtitulo': 'Dica de uso',
            'titulo': 'Não precisa processar aos poucos',
            'paragrafos': [
                'O sistema roda *várias páginas em paralelo*. Isso significa '
                'que mandar tudo de uma vez é bem mais rápido do que dividir '
                'em vários envios pequenos.',
                'Se você tem um processo inteiro para converter, mande o '
                'documento completo — a IA organiza tudo em uma planilha só.',
            ],
            'cta': ('Processar um lote', 'app'),
        },
        {
            'assunto': 'O que você achou da planilha?',
            'subtitulo': 'Uma pergunta rápida',
            'titulo': 'Queria saber sua opinião',
            'paragrafos': [
                'Você testou o Sistema Ponto e processou {usadas} páginas. '
                'A planilha saiu do jeito que você esperava?',
                'Se alguma coisa veio errada ou faltou algo, *responda este '
                'e-mail* me contando. Leio todas as respostas e é assim que '
                'a gente melhora a leitura.',
            ],
            'cta': ('Voltar ao sistema', 'app'),
        },
        {
            'assunto': 'Holerite também vira Excel',
            'subtitulo': 'O outro serviço',
            'titulo': 'Você testou os cartões. E os contracheques?',
            'paragrafos': [
                'Além dos cartões de ponto, o sistema extrai *verbas de '
                'holerites*: salário, horas extras, INSS, FGTS, adicionais — '
                'você escolhe quais quer.',
                'Sai um Excel com uma aba por funcionário, organizado por mês. '
                'Suas {restantes} páginas valem para os dois serviços.',
            ],
            'cta': ('Testar com holerites', 'app'),
        },
    ],

    # ══════════════════════════════════════════════════════════════
    # C · ESGOTOU — usou as 50 e não assinou
    # ══════════════════════════════════════════════════════════════
    'C': [
        {
            'assunto': 'Quanto tempo você gastaria digitando aquilo à mão?',
            'subtitulo': 'Sobre o seu teste',
            'titulo': 'Você processou 50 páginas',
            'paragrafos': [
                'Cinquenta páginas de cartão de ponto digitadas à mão são '
                'algumas horas de trabalho — e cada linha é uma chance de '
                'errar um horário.',
                'No plano Básico, *200 páginas por mês* saem por R$ 179,90. '
                'Vale fazer a conta com o valor da sua hora.',
            ],
            'cta': ('Ver planos', 'planos'),
        },
        {
            'assunto': 'Continue de onde parou',
            'subtitulo': 'Escolha seu plano',
            'titulo': 'Seus documentos continuam esperando conversão',
            'paragrafos': [
                'Suas páginas grátis acabaram, mas o sistema continua aqui. '
                'É só escolher um plano que caiba no seu volume:',
            ],
            'cta': ('Assinar agora', 'planos'),
            'planos': True,
        },
        {
            'assunto': 'Novidades desde que você testou',
            'subtitulo': 'O que melhorou',
            'titulo': 'O sistema mudou desde a sua última visita',
            'paragrafos': [
                'O foco tem sido *precisão de leitura*: mais layouts '
                'reconhecidos, melhor tratamento de turnos que viram a noite '
                'e menos correção manual nas marcações.',
                'Se você teve algum problema quando testou, provavelmente '
                'já está resolvido.',
            ],
            'cta': ('Ver planos', 'planos'),
        },
        {
            'assunto': 'Páginas extras nunca bloqueiam seu trabalho',
            'subtitulo': 'Como funciona a cobrança',
            'titulo': 'E se eu passar do limite do plano?',
            'paragrafos': [
                'Nada acontece — você *não é bloqueado*. As páginas que '
                'passarem do plano são cobradas automaticamente na fatura '
                'seguinte, a partir de R$ 0,70 cada.',
                'Isso quer dizer que um mês de volume alto não trava seu '
                'trabalho no meio de um processo.',
            ],
            'cta': ('Ver planos', 'planos'),
            'planos': True,
        },
        {
            'assunto': 'Ficou com dúvida sobre os planos?',
            'subtitulo': 'Posso ajudar',
            'titulo': 'Alguma dúvida sobre assinar?',
            'paragrafos': [
                'Você testou o sistema até o fim das páginas grátis e não '
                'assinou. Se ficou alguma dúvida — sobre preço, volume, '
                'formato de arquivo, qualquer coisa — *é só responder este '
                'e-mail*.',
                'Se preferir, me conta qual é o seu volume mensal que eu '
                'te digo qual plano faz mais sentido.',
            ],
            'cta': ('Ver planos', 'planos'),
        },
    ],

    # ══════════════════════════════════════════════════════════════
    # D · EX-ASSINANTE — pagou e cancelou
    # ══════════════════════════════════════════════════════════════
    'D': [
        {
            'assunto': 'O que mudou no Sistema Ponto desde a sua última assinatura',
            'subtitulo': 'Novidades por aqui',
            'titulo': 'Algumas coisas melhoraram desde que você saiu',
            'paragrafos': [
                'Você já foi assinante, então talvez valha saber no que '
                'trabalhamos desde então.',
                'O foco foi *precisão de leitura*: mais layouts de cartão de '
                'ponto reconhecidos, melhor tratamento de turnos que viram a '
                'noite e menos correção manual nas marcações.',
            ],
            'cta': ('Ver planos', 'planos'),
            'planos': True,
            'rodape': 'Se alguma coisa deixou a desejar, me conta respondendo este e-mail.',
        },
        {
            'assunto': 'Nova perícia à vista?',
            'subtitulo': 'Quando o volume voltar',
            'titulo': 'A gente continua aqui',
            'paragrafos': [
                'Sabemos que a demanda vai e volta: termina um processo, o '
                'volume cai; entra outro, e de repente são centenas de páginas '
                'para converter.',
                'Quando esse dia chegar, *reativar leva um minuto* — mesma '
                'conta, mesmo login.',
            ],
            'cta': ('Reativar meu plano', 'planos'),
        },
        {
            'assunto': 'Seus planos continuam disponíveis',
            'subtitulo': 'Sempre que precisar',
            'titulo': 'Reative quando fizer sentido',
            'paragrafos': [
                'Sua conta continua ativa e o processamento pode voltar a '
                'qualquer momento. Os planos são estes:',
            ],
            'cta': ('Reativar', 'planos'),
            'planos': True,
        },
        {
            'assunto': 'Posso te fazer uma pergunta?',
            'subtitulo': 'Sua opinião ajuda',
            'titulo': 'Por que você cancelou?',
            'paragrafos': [
                'Você assinou o Sistema Ponto e depois cancelou. Queria '
                'entender o que aconteceu: foi o preço, foi alguma coisa que '
                'não funcionou como esperava, ou simplesmente terminou a '
                'demanda que você tinha?',
                '*Responder leva meio minuto* e me ajuda de verdade a '
                'melhorar o sistema. Leio todas.',
            ],
            'cta': ('Ver planos', 'planos'),
        },
    ],
}


def tamanho(pool: str) -> int:
    return len(POOLS.get(pool) or [])


def item(pool: str, indice: int) -> dict:
    lista = POOLS.get(pool) or POOLS['A']
    return lista[indice % len(lista)]
