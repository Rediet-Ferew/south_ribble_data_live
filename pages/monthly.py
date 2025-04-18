import dash
from dash import dcc, html, dash_table
import plotly.express as px
import pandas as pd
import io
import base64
import json
import os
from dash.dependencies import Input, Output, State
from dash import dcc, html, dash_table, Input, Output, callback

dash.register_page(__name__, path="/monthly", name="Monthly Data")


PROCESSED_DATA_FILE = os.path.join(os.getcwd(), "assets", "monthly_output_data.json")
FIRST_VISIT_DATES = os.path.join(os.getcwd(), "assets", "first_visits_string.json")

def load_processed_data():
    if os.path.exists(PROCESSED_DATA_FILE):
        with open(PROCESSED_DATA_FILE, 'r') as f:
            return json.load(f)
    return None

layout = html.Div([

    dcc.Store(id='monthly-stored-data'),
    html.H2("📆 Monthly Breakdown"),

    dcc.Upload(
        id="upload-data-monthly",
        children=html.Button("Upload CSV", className="btn btn-primary"),
        multiple=False,
    ),

    html.Div(id="file-name-monthly", style={"margin": "10px 0"}),

    dcc.Tabs([
        dcc.Tab(label='📊 Breakdown', children=[
            dcc.Loading(
                id="loading-breakdown-monthly",
                type="default",
                children=[
                    html.Div(id="summary-cards-monthly", className="summary-cards"),
                    html.Div(id="monthly-graph-container"),
                    html.Div(id="monthly-table-container"),
                ],
            )
        ]),
        dcc.Tab(label='💡 LTV Analysis', children=[
            dcc.Loading(
                id="loading-ltv-monthly",
                type="default",
                children=[
                    html.Div(id="ltv-content-monthly")
                ]
            )
        ])
    ])
])


# /
# Function to clean and merge CSV data
def clean_and_merge_data(contents_list):
    dfs = []
    for content in contents_list:
        content_type, content_string = content.split(',')
        decoded = base64.b64decode(content_string)
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), index_col=False)
        dfs.append(df)

    merged_df = pd.concat(dfs, ignore_index=True)
    df_needed = merged_df[['PHONE NO', 'DRIVER PRICE', 'JOB DATE']]
    df_needed.columns = ['phone', 'price', 'job_date']
    df_cleaned = df_needed[df_needed["phone"].notna() & (df_needed["phone"] != "")]

    df_cleaned['phone'] = df_cleaned['phone'].astype(str).str.strip()
    df_cleaned.loc[:, "job_date"] = pd.to_datetime(df_cleaned["job_date"], format="%d/%m/%y %H:%M:%S", errors='coerce', dayfirst=True).dt.date

    return df_cleaned


def safe_parse_date(date_str):
    try:
        return pd.to_datetime(date_str, format='%Y-%m-%d', errors='coerce')
    except Exception:
        return pd.NaT

def monthly_breakdown(df):
    # Ensure job_date is datetime
    df['job_date'] = pd.to_datetime(df['job_date'], errors='coerce')
    df['month'] = df['job_date'].dt.to_period('M')
    
    # Load existing first visit data from JSON
    if os.path.exists(FIRST_VISIT_DATES):
        with open(FIRST_VISIT_DATES, 'r') as f:
            first_visit_data = json.load(f)
    else:
        first_visit_data = []

    # Convert existing JSON data into a dict for quick access
    json_lookup = {
        entry['phone'].strip(): safe_parse_date(entry['first_visit_date'])
        for entry in first_visit_data
    }

    new_entries = []

    # Compute first visit per phone from DataFrame
    phone_min_dates = df.groupby('phone')['job_date'].min().reset_index()
    phone_min_dates.columns = ['phone', 'df_first_visit']

    # Determine actual first visit date using JSON or fallback
    def resolve_first_visit(row):
        phone = row['phone'].strip()
        if phone in json_lookup and pd.notna(json_lookup[phone]):
            return json_lookup[phone]
        else:
            # Add to new entries to update JSON later
            visit_date_str = row['df_first_visit'].strftime('%Y-%m-%d') if pd.notna(row['df_first_visit']) else None
            if visit_date_str:
                new_entries.append({
                    'phone': phone,
                    'first_visit_date': visit_date_str
                })
            return row['df_first_visit']

    phone_min_dates['first_visit_date'] = phone_min_dates.apply(resolve_first_visit, axis=1)
    df = pd.merge(df, phone_min_dates[['phone', 'first_visit_date']], on='phone', how='left')
    df['first_visit_month'] = df['first_visit_date'].dt.to_period('M')

    # Monthly breakdown calculation
    monthly_results = []
    for month in sorted(df['month'].unique()):
        month_data = df[df['month'] == month]
        total_customers = month_data['phone'].nunique()
        new_customers = month_data[month_data['month'] == month_data['first_visit_month']]['phone'].nunique()
        returning_customers = total_customers - new_customers

        new_percentage = round((new_customers / total_customers * 100), 2) if total_customers > 0 else 0
        returning_percentage = round((returning_customers / total_customers * 100), 2) if total_customers > 0 else 0

        month_revenue = month_data['price'].sum()
        new_revenue = month_data[month_data['month'] == month_data['first_visit_month']]['price'].sum()
        returning_revenue = month_revenue - new_revenue

        monthly_results.append({
            'month': str(month),
            'total_customers': total_customers,
            'new_customers': new_customers,
            'returning_customers': returning_customers,
            'new_percentage': new_percentage,
            'returning_percentage': returning_percentage,
            'total_revenue': month_revenue,
            'new_customer_revenue': new_revenue,
            'returning_customer_revenue': returning_revenue
        })

    monthly_df = pd.DataFrame(monthly_results)

    # LTV calculations
    total_revenue = df['price'].sum()
    unique_customers = df['phone'].nunique()
    basic_ltv = total_revenue / unique_customers if unique_customers > 0 else 0

    avg_purchase_value = total_revenue / len(df) if len(df) > 0 else 0
    avg_purchase_frequency = len(df) / unique_customers if unique_customers > 0 else 0

    df_sorted = df.sort_values(['phone', 'job_date'])
    df_sorted['next_visit'] = df_sorted.groupby('phone')['job_date'].shift(-1)
    df_sorted['days_between_visits'] = (df_sorted['next_visit'] - df_sorted['job_date']).dt.days

    avg_days_between_visits = df_sorted['days_between_visits'].mean() if not df_sorted['days_between_visits'].isna().all() else 1
    churn_threshold = 180
    avg_customer_lifespan = churn_threshold / avg_days_between_visits if avg_days_between_visits > 0 else 0

    advanced_ltv = avg_purchase_value * avg_purchase_frequency * avg_customer_lifespan

    # Append new entries to the JSON and save (avoiding duplicates)
    if new_entries:
        # Merge with existing but avoid duplicates
        existing_phones = {entry['phone'] for entry in first_visit_data}
        updated_json = first_visit_data + [entry for entry in new_entries if entry['phone'] not in existing_phones]
        with open(FIRST_VISIT_DATES, 'w') as f:
            json.dump(updated_json, f, indent=4)

    return {
        'monthly_breakdown': monthly_df,
        'Basic LTV': basic_ltv,
        'Advanced LTV': advanced_ltv,
        'Average Purchase Value': avg_purchase_value,
        'Average Purchase Frequency': avg_purchase_frequency,
        'Average Customer LifeSpan (Months)': avg_customer_lifespan
    }
def generate_visuals(df):
    # Increase figure size and adjust layout
    fig_line = px.line(df, x='month', y=['new_customers', 'returning_customers'], markers=True)
    fig_line.update_layout(width=2000, height=500, margin={"r": 20, "t": 20, "l": 20, "b": 50})

    # Increase bar width and ensure bars are not too thin
    fig_bar = px.bar(
        df,
        x='month',
        y=['total_revenue', 'new_customer_revenue', 'returning_customer_revenue'],
        barmode='group'
    )
    fig_bar.update_layout(
        width=2500,
        height=600,
        margin={"r": 20, "t": 20, "l": 20, "b": 100},
        bargap=0.2,
        xaxis=dict(tickangle=45),
    )

    return html.Div([
        html.H2("📊 Data Table"),
        dash_table.DataTable(
            columns=[{"name": col, "id": col} for col in df.columns],
            data=df.round(2).to_dict('records'),
            style_table={'overflowX': 'auto'}
        ),
        html.H2("📈 Monthly Trends"),

        dcc.Graph(figure=fig_line),

        html.Div(
            dcc.Graph(figure=fig_bar),
            style={'overflowX': 'scroll', 'width': '100%', 'whiteSpace': 'nowrap'}
        ),
    ])



@dash.callback(
    [Output('monthly-stored-data', 'data'),
     Output('file-name-monthly', 'children', allow_duplicate=True),
     Output('monthly-graph-container', 'children'),
     Output('monthly-table-container', 'children'),
     Output('ltv-content-monthly', 'children')],
    [Input('upload-data-monthly', 'contents'),
     Input('url', 'pathname')],
    [State('monthly-stored-data', 'data')],
    prevent_initial_call='initial_duplicate'
)
def unified_callback(contents, pathname, stored_data):
    ctx = dash.callback_context
    
    # Default returns
    new_stored_data = dash.no_update
    file_message = dash.no_update
    graphs = "📥 Upload a file to see graphs"
    table = ""
    ltv_content = ""
    
    if not ctx.triggered:
        existing_data = load_processed_data()
        if existing_data:
            # Convert monthly_breakdown list to DataFrame for display
            monthly_df = pd.DataFrame(existing_data['monthly_breakdown'])
            graphs = generate_visuals(monthly_df)
            ltv_content = create_ltv_cards(existing_data)
            file_message = "✅ Loaded existing data"
            new_stored_data = existing_data
        else:
            file_message = "📭 No data available"
        return new_stored_data, file_message, graphs, table, ltv_content
    
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger == 'upload-data-monthly' and contents:
        try:
            new_df = clean_and_merge_data([contents])
            existing_data = load_processed_data() or {}
           
            processed_data = monthly_breakdown(new_df)

            new_monthly_breakdown = processed_data['monthly_breakdown'].to_dict(orient='records')
            existing_data = load_processed_data()
            if existing_data:
                existing_monthly_breakdown = existing_data.get('monthly_breakdown', [])
                
                # Ensure existing_weekly_breakdown is a list before appending
                if not isinstance(existing_monthly_breakdown, list):
                    existing_monthly_breakdown = []
                
                # Append new data
                processed_data['monthly_breakdown'] = existing_monthly_breakdown + new_monthly_breakdown
            else:
                processed_data['monthly_breakdown'] = new_monthly_breakdown

            # Save the processed data to file
            with open(PROCESSED_DATA_FILE, 'w') as f:
                json.dump(processed_data, f, indent=4)  # Pretty print for readability
            
           
            file_message = "✅ File uploaded & processed!"
            
            # Generate visuals with the processed DataFrame
            final_data = load_processed_data()
            monthly_df = pd.DataFrame(final_data['monthly_breakdown'])
            graphs = generate_visuals(pd.DataFrame(monthly_df))
            ltv_content = create_ltv_cards(processed_data)
            
        except Exception as e:
            file_message = f"⚠️ Error: {str(e)}"
            return dash.no_update, file_message, dash.no_update, dash.no_update, dash.no_update
    
    elif trigger == 'url':
        existing_data = load_processed_data()
        if existing_data:
            # Convert list to DataFrame for display
            monthly_df = pd.DataFrame(existing_data['monthly_breakdown'])
            graphs = generate_visuals(monthly_df)
            ltv_content = create_ltv_cards(existing_data)
            file_message = "✅ Loaded existing data"
            new_stored_data = existing_data
        else:
            file_message = "📭 No data available"
    
    return new_stored_data, file_message, graphs, table, ltv_content

# Helper function for LTV cards
def create_ltv_cards(data):
    return html.Div([
        html.Div([
            html.Div([html.H3(f"${data['Basic LTV']:.2f}"), html.P("Basic LTV")], className="card"),
            html.Div([html.H3(f"${data['Advanced LTV']:.2f}"), html.P("Advanced LTV")], className="card"),
            html.Div([html.H3(f"${data['Average Purchase Value']:.2f}"), html.P("Avg. Purchase Value")], className="card"),
            html.Div([html.H3(f"{data['Average Purchase Frequency']:.2f}"), html.P("Avg. Purchase Frequency")], className="card"),
            html.Div([html.H3(f"{data['Average Customer LifeSpan (Months)']:.2f}"), html.P("Avg. Customer Lifespan")], className="card")
        ], className="dashboard")
    ])