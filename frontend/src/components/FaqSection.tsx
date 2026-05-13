// frontend/src/components/FaqSection.tsx
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileUp,
  Clock,
  Receipt,
  Wallet,
  ShieldCheck,
  LifeBuoy,
  ChevronDown,
  HelpCircle,
  AlertTriangle,
  MessageCircle,
  type LucideIcon,
} from "lucide-react";

// ───────────────────────────────────────────────────────────
// Conteúdo do FAQ (extraído do PDF "PASSO A PASSO SISTEMA PONTO")
// ───────────────────────────────────────────────────────────
type FaqItem = { q: string; a: string; warning?: boolean };
type FaqCategory = {
  id: string;
  title: string;
  shortTitle: string;
  icon: LucideIcon;
  items: FaqItem[];
};

const FAQ_DATA: FaqCategory[] = [
  {
    id: "pdf",
    title: "Sobre o PDF e o upload de arquivos",
    shortTitle: "PDF e upload",
    icon: FileUp,
    items: [
      {
        q: "Posso enviar um PDF com outros documentos misturados aos cartões ponto?",
        a: "Sim. Você pode enviar o processo inteiro em PDF e informar apenas o intervalo de páginas onde estão os cartões ponto. O sistema processa somente as páginas indicadas e ignora o restante do documento.",
      },
      {
        q: "Os cartões ponto precisam estar em ordem cronológica?",
        a: "Não. O sistema identifica automaticamente o período (data de início e fim) de cada página. A planilha final é organizada em ordem cronológica independentemente da ordem em que as páginas aparecem no PDF.",
      },
      {
        q: "O sistema aceita PDF digitalizado (escaneado)?",
        a: "Sim. A inteligência artificial interpreta os documentos visualmente — funciona tanto com PDFs digitais quanto com documentos escaneados.",
      },
      {
        q: "O PDF precisa estar desbloqueado (sem senha)?",
        a: "Sim. PDFs protegidos por senha não podem ser processados. Caso o arquivo esteja bloqueado, remova a senha antes do upload.",
      },
    ],
  },
  {
    id: "ponto",
    title: "Sobre o Extrator de Ponto",
    shortTitle: "Extrator de Ponto",
    icon: Clock,
    items: [
      {
        q: "O sistema lida com cartões com mais de um turno por dia?",
        a: "Sim. O sistema extrai todas as marcações do dia (Entrada 1, Saída 1, Entrada 2, Saída 2, e assim por diante), conforme constam no cartão ponto original.",
      },
      {
        q: "O que acontece com dias sem marcação (feriados, folgas)?",
        a: "O sistema gera o calendário completo do período. Os dias sem marcação aparecem na planilha com as células vazias, preservando a linha do tempo sem lacunas.",
      },
      {
        q: "Posso corrigir os períodos identificados antes de confirmar a extração?",
        a: 'Sim. Após a identificação automática, o sistema exibe uma tela de validação onde você pode revisar e editar as datas antes de clicar em "Confirmar e Extrair".',
      },
      {
        q: "E se o intervalo de páginas contiver cartões de mais de um funcionário?",
        a: "O Extrator de Ponto não separa os dados por funcionário. Se o intervalo contiver cartões de pessoas diferentes, o sistema processa tudo como se fosse um único funcionário, gerando uma planilha com marcações misturadas e sem aviso. Sempre informe um intervalo com cartões de apenas um funcionário por vez.",
        warning: true,
      },
    ],
  },
  {
    id: "holerite",
    title: "Sobre o Extrator de Holerite",
    shortTitle: "Extrator de Holerite",
    icon: Receipt,
    items: [
      {
        q: "Posso processar holerites de vários funcionários em um único PDF?",
        a: "Sim. O sistema identifica automaticamente todos os funcionários presentes no PDF. O Excel gerado terá uma aba separada para cada funcionário, com as verbas organizadas por mês.",
      },
      {
        q: "Posso selecionar apenas algumas verbas e ignorar outras?",
        a: "Sim. Após a identificação automática das verbas, o sistema exibe a lista completa e você escolhe quais deseja incluir no Excel. Apenas as verbas selecionadas serão extraídas.",
      },
    ],
  },
  {
    id: "creditos",
    title: "Sobre créditos e planos",
    shortTitle: "Créditos e planos",
    icon: Wallet,
    items: [
      {
        q: "Quando os créditos são descontados — no upload ou no download?",
        a: "Os créditos são descontados no momento do download da planilha. Cada página do PDF processada consome 1 crédito.",
      },
      {
        q: "O que acontece se eu ultrapassar o limite de páginas do meu plano?",
        a: "Nos planos pagos, o acesso nunca é bloqueado. As páginas extras são cobradas automaticamente no próximo ciclo de faturamento via Stripe, conforme a tarifa do seu plano. O plano gratuito (Trial) possui limite rígido de 50 páginas, sem possibilidade de páginas extras.",
      },
      {
        q: "Preciso informar dados de cartão de crédito para usar as 50 páginas grátis?",
        a: "Não. O cadastro é gratuito e as 50 páginas de teste são liberadas imediatamente, sem necessidade de informar dados de pagamento.",
      },
    ],
  },
  {
    id: "privacidade",
    title: "Sobre privacidade e segurança",
    shortTitle: "Privacidade",
    icon: ShieldCheck,
    items: [
      {
        q: "Os documentos ficam armazenados no sistema após o processamento?",
        a: "Não. Os arquivos são processados de forma temporária e excluídos automaticamente após o download. Nenhum dado fica retido em nossos servidores.",
      },
      {
        q: "O sistema está em conformidade com a LGPD?",
        a: "Sim. O Sistema Ponto foi desenvolvido com foco em privacidade. O processamento é temporário, sem armazenamento de informações pessoais, em conformidade com a Lei Geral de Proteção de Dados (LGPD).",
      },
    ],
  },
  {
    id: "suporte",
    title: "Sobre erros e suporte",
    shortTitle: "Suporte",
    icon: LifeBuoy,
    items: [
      {
        q: "O que faço se a planilha gerada tiver informações incorretas?",
        a: "Entre em contato com nosso suporte via WhatsApp (54 99942-7282) enviando o PDF original e a planilha gerada. Vamos analisar, corrigir e treinar o modelo para aquele formato. As páginas em que o sistema apresentou erro serão isentas de cobrança, salvo em casos de erro no uso do sistema pelo usuário.",
      },
      {
        q: "Como aciono o suporte?",
        a: 'Você pode acionar o suporte de duas formas: (1) clicando no ícone com suas iniciais no canto superior direito do sistema e em seguida em "Suporte"; ou (2) diretamente pelo WhatsApp: 54 99942-7282.',
      },
    ],
  },
];

// ───────────────────────────────────────────────────────────
// Item do accordion
// ───────────────────────────────────────────────────────────
interface AccordionItemProps {
  item: FaqItem;
  idx: number;
  isOpen: boolean;
  onToggle: () => void;
}

const AccordionItem = ({ item, idx, isOpen, onToggle }: AccordionItemProps) => (
  <div className={`border-b border-border/30 last:border-b-0 ${isOpen ? "bg-white/[0.02]" : ""}`}>
    <button
      onClick={onToggle}
      className="w-full flex items-start justify-between gap-4 text-left py-5 px-5 hover:bg-white/[0.02] transition-colors"
    >
      <div className="flex items-start gap-3 flex-1 min-w-0">
        <span className="text-xs font-mono text-primary/60 mt-1 tabular-nums shrink-0">
          {String(idx).padStart(2, "0")}
        </span>
        <span className="text-[15px] font-medium text-foreground leading-snug">{item.q}</span>
      </div>
      <div
        className={`shrink-0 w-7 h-7 rounded-full border border-border/40 flex items-center justify-center transition-transform ${
          isOpen ? "rotate-180 border-primary/60 bg-primary/10" : ""
        }`}
      >
        <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
      </div>
    </button>

    <AnimatePresence initial={false}>
      {isOpen && (
        <motion.div
          key="content"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          style={{ overflow: "hidden" }}
        >
          <div className="px-5 pb-5 pl-[3.25rem]">
            {item.warning && (
              <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-lg bg-warning/10 border border-warning/30 w-fit">
                <AlertTriangle className="w-4 h-4 text-warning shrink-0" />
                <span className="text-xs font-semibold text-warning uppercase tracking-wider">
                  Atenção
                </span>
              </div>
            )}
            <p className="text-sm text-muted-foreground leading-relaxed">{item.a}</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  </div>
);

// ───────────────────────────────────────────────────────────
// Seção FAQ — variante "Categorias"
// ───────────────────────────────────────────────────────────
const FaqSection = () => {
  const [activeCat, setActiveCat] = useState(FAQ_DATA[0].id);
  const [openKey, setOpenKey] = useState<string | null>(`${FAQ_DATA[0].id}-0`);
  const cat = FAQ_DATA.find((c) => c.id === activeCat) ?? FAQ_DATA[0];
  const CatIcon = cat.icon;

  return (
    <section id="faq" className="py-20 px-6 relative">
      {/* Glow sutil ao fundo */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-primary/5 rounded-full blur-3xl" />
      </div>

      <div className="container mx-auto relative z-10">
        {/* Header da seção */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-12"
        >
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-primary/30 bg-primary/10 mb-6">
            <HelpCircle className="w-4 h-4 text-primary" />
            <span className="text-sm text-primary font-medium">Perguntas frequentes</span>
          </div>
          <h3 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Tudo o que você precisa saber
          </h3>
          <p className="text-muted-foreground max-w-xl mx-auto">
            Respostas rápidas para as dúvidas mais comuns sobre o Sistema Ponto.
          </p>
        </motion.div>

        {/* Layout: sidebar (categorias) + conteúdo (accordion) */}
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6 max-w-5xl mx-auto">
          {/* Sidebar com categorias */}
          <aside className="lg:sticky lg:top-24 lg:self-start">
            <div className="glass-card p-2">
              <div className="px-3 py-2 text-[10px] font-bold tracking-[0.15em] text-muted-foreground uppercase">
                Categorias
              </div>
              <nav className="flex flex-col gap-0.5">
                {FAQ_DATA.map((c) => {
                  const Icon = c.icon;
                  const active = activeCat === c.id;
                  return (
                    <button
                      key={c.id}
                      onClick={() => {
                        setActiveCat(c.id);
                        setOpenKey(`${c.id}-0`);
                      }}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-sm transition-all ${
                        active
                          ? "bg-primary/15 text-foreground"
                          : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
                      }`}
                    >
                      <span
                        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                          active
                            ? "gradient-primary text-primary-foreground"
                            : "bg-white/5 text-muted-foreground"
                        }`}
                      >
                        <Icon className="w-4 h-4" />
                      </span>
                      <span className="flex-1 leading-tight">{c.shortTitle}</span>
                      <span className="text-[10px] font-mono tabular-nums opacity-60">
                        {c.items.length}
                      </span>
                    </button>
                  );
                })}
              </nav>
            </div>
          </aside>

          {/* Conteúdo da categoria ativa */}
          <motion.div
            key={cat.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="glass-card overflow-hidden"
          >
            <div className="px-5 py-4 border-b border-border/40 flex items-center gap-3">
              <span className="w-9 h-9 rounded-lg gradient-primary text-primary-foreground flex items-center justify-center">
                <CatIcon className="w-4 h-4" />
              </span>
              <div>
                <h4 className="text-base font-bold text-foreground">{cat.title}</h4>
                <p className="text-xs text-muted-foreground">
                  {cat.items.length} perguntas nesta categoria
                </p>
              </div>
            </div>
            <div>
              {cat.items.map((item, i) => {
                const key = `${cat.id}-${i}`;
                return (
                  <AccordionItem
                    key={key}
                    item={item}
                    idx={i + 1}
                    isOpen={openKey === key}
                    onToggle={() => setOpenKey(openKey === key ? null : key)}
                  />
                );
              })}
            </div>
          </motion.div>
        </div>

        {/* CTA de suporte */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mt-12 max-w-3xl mx-auto"
        >
          <div className="glass-card p-6 md:p-8 flex flex-col md:flex-row items-center gap-6 text-center md:text-left">
            <div className="w-14 h-14 rounded-2xl gradient-primary flex items-center justify-center shrink-0">
              <MessageCircle className="w-6 h-6 text-primary-foreground" />
            </div>
            <div className="flex-1">
              <h4 className="text-base font-bold text-foreground mb-1">
                Não encontrou sua resposta?
              </h4>
              <p className="text-sm text-muted-foreground">
                Fale com o nosso suporte pelo WhatsApp{" "}
                <span className="text-foreground font-medium">(54) 99942-7282</span>.
              </p>
            </div>
            <a
              href="https://wa.me/5554999427282"
              target="_blank"
              rel="noopener noreferrer"
              className="px-5 py-2.5 rounded-lg bg-white/5 hover:bg-white/10 border border-border/40 hover:border-primary/40 text-sm font-semibold text-foreground transition-all whitespace-nowrap"
            >
              Falar com suporte →
            </a>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default FaqSection;

