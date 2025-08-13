import React, { useState } from 'react';
import Login from '@/components/Login';

const Index = () => {
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  const handleLogin = () => {
    setIsLoggedIn(true);
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
  };

  if (!isLoggedIn) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-gradient-background p-6">
      <div className="max-w-4xl mx-auto">
        <div className="bg-card/80 backdrop-blur-xl rounded-xl p-8 shadow-card border border-border/50">
          <div className="flex justify-between items-center mb-8">
            <div>
              <h1 className="text-3xl font-bold text-foreground">
                Sistema Pontua
              </h1>
              <p className="text-muted-foreground">
                Bem-vindo ao sistema de automação de cartão ponto
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="px-4 py-2 bg-primary/10 hover:bg-primary/20 text-primary rounded-lg transition-colors duration-300 border border-primary/20"
            >
              Sair
            </button>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 bg-gradient-to-br from-primary/10 to-primary/5 rounded-xl border border-primary/20">
              <h3 className="text-xl font-semibold mb-2 text-foreground">
                Registros Hoje
              </h3>
              <p className="text-3xl font-bold text-primary">24</p>
            </div>
            
            <div className="p-6 bg-gradient-to-br from-primary/10 to-primary/5 rounded-xl border border-primary/20">
              <h3 className="text-xl font-semibold mb-2 text-foreground">
                Funcionários Ativos
              </h3>
              <p className="text-3xl font-bold text-primary">12</p>
            </div>
            
            <div className="p-6 bg-gradient-to-br from-primary/10 to-primary/5 rounded-xl border border-primary/20">
              <h3 className="text-xl font-semibold mb-2 text-foreground">
                Horas Trabalhadas
              </h3>
              <p className="text-3xl font-bold text-primary">96h</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Index;
