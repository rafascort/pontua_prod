import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

const TermosPage = () => {
  return (
    <div className="min-h-screen gradient-bg">
      <header className="sticky top-0 z-50 bg-background/60 backdrop-blur-xl border-b border-border/30">
        <div className="container mx-auto flex items-center gap-4 py-4 px-6">
          <Link to="/" className="text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <h1 className="text-xl font-bold text-foreground">Termos de Uso</h1>
        </div>
      </header>

      <main className="container mx-auto max-w-3xl px-6 py-12">
        <div className="glass-card p-8 space-y-8">
          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">1. Aceitação dos Termos</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Ao acessar e utilizar o Sistema Ponto, você concorda com estes Termos de Uso. 
              Caso não concorde com alguma disposição, solicitamos que não utilize a plataforma.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">2. Descrição do Serviço</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              O Sistema Ponto é uma plataforma de extração inteligente de dados de documentos 
              trabalhistas (cartões de ponto e holerites) utilizando Inteligência Artificial. 
              O serviço processa arquivos PDF enviados pelo usuário e retorna os dados extraídos 
              em formato estruturado.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">3. Cadastro e Conta</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Para utilizar o serviço, é necessário criar uma conta fornecendo informações válidas. 
              Ao se cadastrar, o usuário recebe um bônus de 50 páginas gratuitas (Free Trial). 
              O usuário é responsável por manter a confidencialidade de suas credenciais de acesso.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">4. Planos e Pagamentos</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              O Sistema Ponto oferece planos de assinatura com diferentes limites de páginas. 
              Os pagamentos são processados de forma segura via Stripe. As assinaturas são 
              renovadas automaticamente conforme o ciclo do plano contratado. O cancelamento 
              pode ser solicitado a qualquer momento e será efetivado ao final do período vigente.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">5. Uso Aceitável</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              O usuário compromete-se a utilizar o serviço apenas para fins legítimos e em 
              conformidade com a legislação vigente. É proibido o uso do sistema para processar 
              documentos falsificados, fraudulentos ou de origem ilícita. O uso abusivo ou 
              automatizado excessivo pode resultar na suspensão da conta.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">6. Privacidade e Dados</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Os documentos enviados são processados exclusivamente para fins de extração de dados 
              e não são armazenados permanentemente em nossos servidores após o processamento. 
              Respeitamos a Lei Geral de Proteção de Dados (LGPD) e garantimos que as informações 
              pessoais dos usuários são tratadas com segurança e transparência.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">7. Limitação de Responsabilidade</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              O Sistema Ponto não se responsabiliza por erros na extração de dados decorrentes 
              de documentos de baixa qualidade, ilegíveis ou em formatos não suportados. 
              Recomendamos que o usuário sempre verifique os dados extraídos antes de utilizá-los.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">8. Modificações dos Termos</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Reservamo-nos o direito de atualizar estes Termos de Uso a qualquer momento. 
              As alterações serão comunicadas por e-mail ou notificação na plataforma. O uso 
              contínuo do serviço após as alterações implica na aceitação dos novos termos.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">9. Contato</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Em caso de dúvidas sobre estes Termos de Uso, entre em contato conosco pelo 
              e-mail <span className="text-primary font-medium">suporte@sistemaponto.com.br</span>.
            </p>
          </section>

          <div className="pt-4 border-t border-border/30">
            <p className="text-xs text-muted-foreground">Última atualização: Março de 2026</p>
          </div>
        </div>
      </main>
    </div>
  );
};

export default TermosPage;
