import dash
from dash import html

dash.register_page(__name__, path="/", name="Home")

layout = html.Div([
    html.H2("Welcome to South Ribble Data Dashboard", className="text-center mt-4"),
    html.Div([
        html.P("📊 Explore your data using the navigation bar above:"),
        html.Ul([
            html.Li("Click WEEKLY for weekly metrics"),
            html.Li("Click MONTHLY for monthly trends"),
            html.Li("Click WEEKLY-AIRPORT for weekly airport trip trends"),
            html.Li("Click MONTHLY-AIRPORT for monthly airport trip trends"),
        ]),
        html.P("💾 Remember to upload your CSV files using the upload button"),
        html.P("🔍 Data updates may take a few moments to process")
    ], style={
        'max-width': '800px',
        'margin': '40px auto',
        'padding': '20px',
        'border': '2px solid #0275d8',
        'border-radius': '10px',
        'background-color': '#f8f9fa'
    })
])
