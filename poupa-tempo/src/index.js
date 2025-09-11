    // src/index.js
    import React from 'react';
    import ReactDOM from 'react-dom/client';
    import { BrowserRouter } from 'react-router-dom'; // <--- ADICIONAR ESTA LINHA
    import App from './App';
    import reportWebVitals from './reportWebVitals';
    // import './index.css'; // Descomente se você tiver um arquivo index.css

    const root = ReactDOM.createRoot(document.getElementById('root'));
    root.render(
      <React.StrictMode>
        <BrowserRouter> {/* <--- ENVOLVER O <App /> COM <BrowserRouter> */}
          <App />
        </BrowserRouter>
      </React.StrictMode>
    );

    reportWebVitals();

