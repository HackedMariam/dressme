# Lance le service RAG (conseils de mode tirés de livres, avec sources) sur le port 8010.
# L'AI Stylist (BO1) l'appelle comme un outil ; sans lui, le stylist répond avec la garde-robe seule.
# Utilisable depuis n'importe quel dossier :   .\start_rag.ps1
# Table de connaissances : knowledge_chunks_v2 (corpus nettoyé + nouvelles sources, le meilleur score de docs/rag_v2/results.md).
param([int]$Port = 8010)

# Peu de mémoire virtuelle sur cette machine : un seul thread BLAS évite les "OpenBLAS error: Memory allocation failed".
if (-not $env:OPENBLAS_NUM_THREADS) { $env:OPENBLAS_NUM_THREADS = "1" }
if (-not $env:OMP_NUM_THREADS) { $env:OMP_NUM_THREADS = "1" }
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $env:RAG_TABLE) { $env:RAG_TABLE = "knowledge_chunks_v2" }
Write-Host "RAG : http://127.0.0.1:$Port/health  (table $($env:RAG_TABLE), Ctrl+C pour arrêter)"
Set-Location (Join-Path $Root "rag_backend")
python -m uvicorn app:app --host 127.0.0.1 --port $Port
