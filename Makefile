.PHONY: setup pipeline dashboard

setup:
	python -m pip install --upgrade pip && python -m pip install -e ".[analysis,dashboard]"

pipeline:
	python load_data.py
	python -m immune_cell_analytics.analysis
	python -m immune_cell_analytics.stats
	python -m immune_cell_analytics.subsets

dashboard:
	streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
