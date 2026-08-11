import pandas as pd
import plotly.express as px
import plotly.io as pio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HISTORY_CSV = BASE_DIR / "history" / "ots_history.csv"
TEMPLATE_FILE = BASE_DIR / "templates" / "ots_dashboard_template.html"
OUTPUT_FILE = BASE_DIR / "output" / "ots_dashboard.html"

def generate_dashboard():
    print(f"Reading OTS data from {HISTORY_CSV}...")
    if not HISTORY_CSV.exists():
        print(f"Error: {HISTORY_CSV} does not exist.")
        return
        
    df = pd.read_csv(HISTORY_CSV)
    
    # We will filter to 'DELHI' for the default premium view, but you can change this
    market = "DELHI"
    df_market = df[df["Market"] == market].copy()
    
    if df_market.empty:
        print(f"Warning: No data found for Market = {market}")
        return

    # Clean the OTS column if it's strings instead of float
    df_market["OTS"] = pd.to_numeric(df_market["OTS"], errors="coerce")
    
    # Create the Plotly figure as a bubble chart (scatter)
    fig = px.scatter(
        df_market, 
        x="Week", 
        y="Channel", 
        color="OTS",
        size="OTS",
        color_continuous_scale="Tealgrn",
    )
    
    # Apply premium styling
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Manrope, sans-serif", color="#f8fafc"),
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False, title=""),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False, title=""),
        hovermode="closest",
        coloraxis_colorbar=dict(
            title="OTS %",
            thicknessmode="pixels", thickness=15,
            lenmode="pixels", len=300,
            yanchor="middle", y=0.5
        )
    )
    
    # Customize marker size scaling
    fig.update_traces(marker=dict(sizemin=10, sizemode='area'))
    
    # Generate the raw HTML div string (without wrapping it in <html> tags)
    graph_html = pio.to_html(fig, full_html=False, include_plotlyjs='cdn', config={'responsive': True})
    
    # Read custom template
    if not TEMPLATE_FILE.exists():
        print(f"Error: {TEMPLATE_FILE} does not exist.")
        return
        
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    
    # Inject graph and data into the template
    final_html = template.replace("{{PLOTLY_GRAPH}}", graph_html).replace("{{MARKET_NAME}}", market)
    
    # Save the output
    OUTPUT_FILE.parent.mkdir(exist_ok=True, parents=True)
    OUTPUT_FILE.write_text(final_html, encoding="utf-8")
    print(f"Successfully generated your premium dashboard at {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_dashboard()
