"""Scientific Research Paper Publication Plot Generator.

Generates 300 DPI high-resolution figures for the empirical paper:
1. Fig 1: Latency Distribution Curves (p50, p90, p95, p99)
2. Fig 2: RAM Memory Footprint (Bloom Filter vs Cuckoo Filter)
3. Fig 3: Ablation Study Throughput & Latency Progression across API Versions
4. Fig 4: LLM Token Savings Comparison (Traditional HTTP vs Model Context Protocol MCP)
"""

import os
import matplotlib.pyplot as plt
import seaborn as sns

# Set publication style
plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 13,
})

OUTPUT_DIR = "docs/figures"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def plot_fig1_latency_distribution() -> None:
    """Fig 1: Latency Distribution metrics with 2-line wrapped title."""
    fig, ax = plt.subplots(figsize=(7, 4.8), dpi=300)

    metrics = ["Caché L1", "Cuckoo RAM", "Redis L2", "DNS MX", "p50 Mediana", "p90", "p95", "p99 Tail"]
    values = [0.05, 0.48, 1.85, 18.40, 40.75, 172.08, 240.96, 290.25]
    colors = ["#2ecc71", "#2ecc71", "#3498db", "#f1c40f", "#e67e22", "#e74c3c", "#c0392b", "#8e44ad"]

    bars = ax.barh(metrics, values, color=colors, edgecolor="black", alpha=0.85)

    for bar, val in zip(bars, values):
        ax.text(val + (max(values) * 0.015), bar.get_y() + bar.get_height() / 2, f"{val:.2f} ms",
                va="center", ha="left", fontsize=9, fontweight="bold")

    ax.set_xlabel("Latencia en Milisegundos (ms)")
    ax.set_title("Figura 1: Distribución de Latencias por Etapa\ny Persentiles de Desempeño (p50-p99)", pad=12)
    ax.set_xlim(0, max(values) * 1.15)
    plt.tight_layout()

    out_path = os.path.join(OUTPUT_DIR, "fig1_latency_distribution.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"✅ Generated {out_path}")


def plot_fig2_ram_footprint() -> None:
    """Fig 2: RAM Memory Footprint comparison with 2-line wrapped title."""
    fig, ax = plt.subplots(figsize=(6.5, 4.8), dpi=300)

    engines = ["Filtro de Bloom Clásico\n(Standard m=7.18M bits)", "Cuckoo Filter Optimizado\n(b=4, f=8 bits fingerprint)"]
    ram_kb = [898.6, 718.0]
    colors = ["#e74c3c", "#2ecc71"]

    bars = ax.bar(engines, ram_kb, color=colors, width=0.45, edgecolor="black", alpha=0.85)

    for bar, val in zip(bars, ram_kb):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 15, f"{val:.1f} KB",
                ha="center", va="bottom", fontsize=11, fontweight="bold")

    # Add delta arrow / text
    ax.annotate("-20.1% Ahorro de RAM\ny Borrado O(1)", xy=(1, 718.0), xytext=(0.55, 830.0),
                arrowprops=dict(facecolor="#27ae60", shrink=0.08, width=2, headwidth=8),
                fontsize=10, fontweight="bold", color="#27ae60")

    ax.set_ylabel("Consumo de Memoria RAM (KB)")
    ax.set_title("Figura 2: Eficiencia de Memoria RAM en Filtros\nBloom Filter vs Cuckoo Filter (N=500,000)", pad=12)
    ax.set_ylim(0, 1080)
    plt.tight_layout()

    out_path = os.path.join(OUTPUT_DIR, "fig2_cuckoo_vs_bloom_ram.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"✅ Generated {out_path}")


def plot_fig3_ablation_progression() -> None:
    """Fig 3: Ablation Study Version Progression with 2-line wrapped title."""
    fig, ax1 = plt.subplots(figsize=(7.5, 4.8), dpi=300)

    versions = ["v1.0.0 (Base)", "v1.1.0 (L1+Batch)", "v1.2.0 (C/Rust)", "v1.3.0 (Cuckoo+MCP)"]
    rps = [122.78, 185.57, 226.01, 226.01]
    p50_ms = [74.47, 48.88, 37.20, 40.75]

    color1 = "#2980b9"
    ax1.set_xlabel("Versión de la Arquitectura API")
    ax1.set_ylabel("Throughput (Solicitudes / Seg - RPS)", color=color1, fontweight="bold")
    line1 = ax1.plot(versions, rps, color=color1, marker="o", linewidth=2.5, markersize=8, label="Throughput (RPS)")
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.set_ylim(100, 260)

    for i, txt in enumerate(rps):
        ax1.annotate(f"{txt:.1f} RPS", (versions[i], rps[i] + 5), ha="center", color=color1, fontweight="bold")

    ax2 = ax1.twinx()
    color2 = "#e67e22"
    ax2.set_ylabel("Latencia Mediana p50 (ms)", color=color2, fontweight="bold")
    line2 = ax2.plot(versions, p50_ms, color=color2, marker="s", linestyle="--", linewidth=2.5, markersize=8, label="Latencia p50 (ms)")
    ax2.tick_params(axis="y", labelcolor=color2)
    ax2.set_ylim(20, 90)

    for i, txt in enumerate(p50_ms):
        ax2.annotate(f"{txt:.1f} ms", (versions[i], p50_ms[i] - 5), ha="center", color=color2, fontweight="bold")

    plt.title("Figura 3: Evolución Histórica de Desempeño\nThroughput (+84.1%) vs Latencia Mediana (-45.3%)", pad=12)
    plt.tight_layout()

    out_path = os.path.join(OUTPUT_DIR, "fig3_ablation_study_progression.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"✅ Generated {out_path}")


def plot_fig4_mcp_token_savings() -> None:
    """Fig 4: LLM Token Savings under MCP with 2-line wrapped title."""
    fig, ax = plt.subplots(figsize=(6.8, 4.8), dpi=300)

    workloads = ["Verificación Individual", "Verificación en Lote (20 Correos)"]
    http_tokens = [192, 2017]
    mcp_tokens = [26, 229]

    x = range(len(workloads))
    width = 0.35

    rects1 = ax.bar([i - width / 2 for i in x], http_tokens, width, label="HTTP Tradicional (OpenAPI/JSON)", color="#e74c3c", edgecolor="black", alpha=0.85)
    rects2 = ax.bar([i + width / 2 for i in x], mcp_tokens, width, label="MCP Tool (FastMCP JSON-RPC)", color="#2ecc71", edgecolor="black", alpha=0.85)

    for bar in rects1:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, yval + (max(http_tokens) * 0.02), f"{yval:,} tkn", ha="center", va="bottom", fontsize=9, fontweight="bold")

    for bar in rects2:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, yval + (max(http_tokens) * 0.02), f"{yval:,} tkn", ha="center", va="bottom", fontsize=9, fontweight="bold")

    # Add reduction labels
    ax.text(0, 120, "-86.5% Tokens", ha="center", fontsize=10, fontweight="bold", color="#27ae60")
    ax.text(1, 400, "-88.6% Tokens\n(8.81x menor)", ha="center", fontsize=10, fontweight="bold", color="#27ae60")

    ax.set_ylabel("Consumo de Tokens del LLM (cl100k_base)")
    ax.set_title("Figura 4: Reducción del Consumo de Tokens LLM\nmediante Model Context Protocol (MCP)", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(workloads)
    ax.legend(loc="upper left")
    ax.set_ylim(0, max(http_tokens) * 1.2)
    plt.tight_layout()

    out_path = os.path.join(OUTPUT_DIR, "fig4_mcp_token_savings.png")
    plt.savefig(out_path, dpi=300)
    plt.close()
    print(f"✅ Generated {out_path}")


if __name__ == "__main__":
    plot_fig1_latency_distribution()
    plot_fig2_ram_footprint()
    plot_fig3_ablation_progression()
    plot_fig4_mcp_token_savings()
