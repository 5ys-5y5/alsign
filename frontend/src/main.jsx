/**
 * Main entry point for the AlSign frontend application
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import AppRouter from './components/AppRouter';
import './styles/global.css';
import './styles/components.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>
);
