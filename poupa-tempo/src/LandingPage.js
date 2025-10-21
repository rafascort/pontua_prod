import React from 'react';
import { Link } from 'react-router-dom'; // Importa o Link para navegação
import './LandingPage.css'; // Importa os estilos que acabamos de criar

const LandingPage = () => {
  return (
    <div className="landing-wrapper">
      <header className="landing-header">
        <div className="landing-container">
          <h1>Sistema Ponto</h1>
          <nav>
            {/* Usa o Link do React Router para navegar para a rota /login */}
            <Link to="/login">Login</Link>
            {/* O link de cadastro aponta para /cadastro. Você precisará criar essa rota e componente */}
            <Link to="/cadastro" className="button-primary">
              Cadastro
            </Link>
          </nav>
        </div>
      </header>

      <main className="landing-main">
        <section id="hero">
          <div className="landing-container">
            <h2>Automatize o Ponto Eletrônico com Inteligência</h2>
            <p>
              Economize tempo, reduza erros e simplifique a gestão de ponto.
              Nossa solução utiliza IA para extrair dados de cartões ponto em
              PDF, independentemente do layout.
            </p>
            {/* Este botão também aponta para a rota de cadastro */}
            <Link to="/cadastro" className="cta-button">
              Comece Agora
            </Link>
          </div>
        </section>

        <section id="features">
          <div className="landing-container">
            <h2>Vantagens e Tecnologias</h2>
            <div className="features-grid">
              <div className="feature-item">
                <h3>Extração Inteligente</h3>
                <p>
                  Utilizamos OCR e Inteligência Artificial para ler e
                  interpretar os dados das marcações de ponto com alta precisão,
                  mesmo em layouts complexos.
                </p>
              </div>
              <div className="feature-item">
                <h3>Compatibilidade Ampla</h3>
                <p>
                  Suporte nativo para diversos formatos de PDF de sistemas de
                  ponto (JBS, PontoMais, BRF, Rudder, Planalto, etc.) e um modelo
                  de IA genérico adaptável.
                </p>
              </div>
              <div className="feature-item">
                <h3>Processamento Eficiente</h3>
                <p>
                  Converta rapidamente múltiplos PDFs em arquivos CSV
                  organizados, prontos para importação em seu sistema de folha
                  de pagamento ou análise.
                </p>
              </div>
              <div className="feature-item">
                <h3>Segurança</h3>
                <p>
                  Seus dados são processados em um ambiente seguro, com
                  autenticação e respeito à privacidade das informações.
                </p>
              </div>
              <div className="feature-item">
                <h3>Validação de Período</h3>
                <p>
                  Confirme os períodos corretos antes do processamento final,
                  garantindo a integridade dos dados, especialmente em modelos
                  sem data completa.
                </p>
              </div>
              <div className="feature-item">
                <h3>Interface Intuitiva</h3>
                <p>
                  Faça o upload dos arquivos, selecione o modelo e processe
                  seus cartões ponto com poucos cliques.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section id="pricing">
          <div className="landing-container">
            <h2>Planos e Preços</h2>
            <table>
              <thead>
                <tr>
                  <th>Plano</th>
                  <th>Valor Mensal (fixo)</th>
                  <th>Páginas incluídas</th>
                  <th>Valor por página extra</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td data-label="Plano">Básico</td>
                  <td data-label="Valor Mensal">
                    <span className="price">R$ 249,90</span>
                    <span className="details"> / mês</span>
                  </td>
                  <td data-label="Páginas incluídas">200 páginas</td>
                  <td data-label="Página extra">
                    <span className="highlight">R$ 1,50</span> por página extra
                  </td>
                </tr>
                <tr>
                  <td data-label="Plano">Padrão</td>
                  <td data-label="Valor Mensal">
                    <span className="price">R$ 449,90</span>
                    <span className="details"> / mês</span>
                  </td>
                  <td data-label="Páginas incluídas">500 páginas</td>
                  <td data-label="Página extra">
                    <span className="highlight">R$ 1,10</span> por página extra
                  </td>
                </tr>
                <tr>
                  <td data-label="Plano">Premium</td>
                  <td data-label="Valor Mensal">
                    <span className="price">R$ 999,90</span>
                    <span className="details"> / mês</span>
                  </td>
                  <td data-label="Páginas incluídas">1.500 páginas</td>
                  <td data-label="Página extra">
                    <span className="highlight">R$ 0,75</span> por página extra
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="landing-container">
          &copy; 2025 Sistema Ponto. Todos os direitos reservados.
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
