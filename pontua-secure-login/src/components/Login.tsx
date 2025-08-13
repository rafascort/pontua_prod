import React, { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { KeyRound, Clock, Shield, AlertCircle } from 'lucide-react';

interface LoginProps {
  onLogin: () => void;
}

const Login: React.FC<LoginProps> = ({ onLogin }) => {
  const [usuario, setUsuario] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErro('');
    
    // Simulando validação async para UX mais realista
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    if (usuario === 'admin' && senha === '1990') {
      onLogin();
    } else {
      setErro('Usuário ou senha inválidos');
    }
    
    setIsLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-background flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_120%,rgba(120,119,198,0.3),rgba(255,255,255,0))]" />
      
      <Card className="w-full max-w-md shadow-card border-border/50 bg-card/80 backdrop-blur-xl relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent" />
        
        <CardHeader className="text-center space-y-4 relative">
          <div className="mx-auto w-16 h-16 bg-gradient-primary rounded-full flex items-center justify-center animate-glow-pulse">
            <KeyRound className="w-8 h-8 text-primary-foreground" />
          </div>
          
          <div className="space-y-2">
            <CardTitle className="text-3xl font-bold bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
              Pontua
            </CardTitle>
            <CardDescription className="text-base text-muted-foreground">
              Automação de Cartão Ponto
            </CardDescription>
          </div>
          
          <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
            <Shield className="w-3 h-3" />
            <span>Sistema Seguro</span>
          </div>
        </CardHeader>

        <CardContent className="relative">
          <form onSubmit={handleLogin} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="usuario" className="text-sm font-medium">
                Usuário
              </Label>
              <Input
                id="usuario"
                type="text"
                placeholder="Digite seu usuário"
                value={usuario}
                onChange={(e) => setUsuario(e.target.value)}
                required
                className="transition-all duration-300"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="senha" className="text-sm font-medium">
                Senha
              </Label>
              <Input
                id="senha"
                type="password"
                placeholder="Digite sua senha"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                required
                className="transition-all duration-300"
              />
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                className="text-sm text-primary hover:text-primary-glow transition-colors duration-300 hover:underline"
              >
                Esqueci minha senha
              </button>
            </div>

            {erro && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive animate-in slide-in-from-top-2 duration-300">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span className="text-sm">{erro}</span>
              </div>
            )}

            <Button
              type="submit"
              variant="login"
              size="lg"
              className="w-full gap-2"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                  Autenticando...
                </>
              ) : (
                <>
                  <KeyRound className="w-4 h-4" />
                  Autenticar
                </>
              )}
            </Button>
          </form>

          <div className="mt-6 pt-6 border-t border-border/50">
            <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
              <div className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                <span>24/7</span>
              </div>
              <div className="w-1 h-1 bg-muted-foreground/50 rounded-full" />
              <div className="flex items-center gap-1">
                <Shield className="w-3 h-3" />
                <span>Criptografado</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Login;