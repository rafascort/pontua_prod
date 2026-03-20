import { motion } from "framer-motion";
import { FileText, Receipt, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import AppHeader from "@/components/AppHeader";

const services = [
  {
    id: "ponto",
    title: "Extrator de Ponto",
    desc: "Extraia dados de cartões de ponto automaticamente com IA. Suporte a múltiplos formatos de PDF.",
    icon: FileText,
    path: "/app/ponto",
    color: "from-primary to-primary/60",
  },
  {
    id: "holerite",
    title: "Extrator de Holerite",
    desc: "Extraia informações de holerites e contracheques com reconhecimento inteligente de campos.",
    icon: Receipt,
    path: "/app/holerite",
    color: "from-success to-success/60",
  },
];

const ServiceSelectionPage = () => {
  return (
    <div className="min-h-screen gradient-bg flex flex-col">
      <AppHeader />

      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-3xl">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center mb-12"
          >
            <h2 className="text-3xl font-bold text-foreground mb-3">Escolha o Serviço</h2>
            <p className="text-muted-foreground">Selecione qual tipo de documento deseja processar</p>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-6">
            {services.map((service, i) => (
              <Link key={service.id} to={service.path}>
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1 }}
                  whileHover={{ y: -6, scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="glass-card-hover p-8 cursor-pointer group h-full"
                >
                  <div className={`w-16 h-16 rounded-2xl bg-gradient-to-br ${service.color} flex items-center justify-center mb-6`}>
                    <service.icon className="w-8 h-8 text-primary-foreground" />
                  </div>
                  <h3 className="text-xl font-bold text-foreground mb-3">{service.title}</h3>
                  <p className="text-muted-foreground text-sm leading-relaxed mb-6">{service.desc}</p>
                  <div className="flex items-center gap-2 text-primary text-sm font-semibold group-hover:gap-3 transition-all">
                    Acessar
                    <ArrowRight className="w-4 h-4" />
                  </div>
                </motion.div>
              </Link>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
};

export default ServiceSelectionPage;
