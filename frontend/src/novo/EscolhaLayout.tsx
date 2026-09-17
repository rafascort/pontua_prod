// frontend/src/novo/EscolhaLayout.tsx
//
// Decide qual das duas telas renderizar.
//
// Regra, nesta ordem:
//   1. Nao e' admin  -> SEMPRE a tela atual. Nao ha' como um cliente cair no
//      layout novo, nem por URL, nem por localStorage.
//   2. E' admin e pediu ?layout=antigo (ou clicou em "ver o antigo") -> atual.
//   3. E' admin      -> layout novo.
//
// E ha' uma rede embaixo: se a tela nova estourar um erro de render, o
// LimiteDeErro devolve a tela atual em vez de deixar a pagina em branco.

import { Component, ReactElement, ReactNode, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

const CHAVE = "sp_layout_extrator";

class LimiteDeErro extends Component<
  { reserva: ReactElement; children: ReactNode },
  { quebrou: boolean }
> {
  state = { quebrou: false };

  static getDerivedStateFromError() {
    return { quebrou: true };
  }

  componentDidCatch(erro: unknown) {
    // eslint-disable-next-line no-console
    console.error("[layout novo] caiu para a tela antiga:", erro);
  }

  render() {
    return this.state.quebrou ? this.props.reserva : <>{this.props.children}</>;
  }
}

export default function EscolhaLayout({
  novo,
  atual,
}: {
  novo: (voltarAoAntigo: () => void) => ReactElement;
  atual: ReactElement;
}) {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [preferencia, setPreferencia] = useState<string | null>(null);

  useEffect(() => {
    const daUrl = params.get("layout");
    if (daUrl === "antigo" || daUrl === "novo") {
      localStorage.setItem(CHAVE, daUrl);
      setPreferencia(daUrl);
      params.delete("layout");
      setParams(params, { replace: true });
      return;
    }
    setPreferencia(localStorage.getItem(CHAVE));
  }, [params, setParams]);

  if (user?.role !== "admin") return atual;
  if (preferencia === "antigo") return atual;

  const voltarAoAntigo = () => {
    localStorage.setItem(CHAVE, "antigo");
    window.location.reload();
  };

  return <LimiteDeErro reserva={atual}>{novo(voltarAoAntigo)}</LimiteDeErro>;
}
