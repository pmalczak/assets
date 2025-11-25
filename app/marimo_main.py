import marimo

__generated_with = "0.18.0"
app = marimo.App(width="medium")


@app.cell
def _():
    from pathlib import Path
    import sys

    project_root = Path().home() / 'PycharmProjects/github_common_py'
    sys.path.append(str(project_root))
    return


@app.cell
def _():
    from main import calculate_assets

    assets = calculate_assets()
    assets = assets.set_index('id')

    return (assets,)


@app.cell
def _(assets):
    assets_table = assets[['typ', 'grupa', 'RODZAJ*', 'data wyceny', 'wartość-pln']]
    assets_table
    return


@app.cell
def _(assets):
    from main import rap1

    rap1(assets)
    return


if __name__ == "__main__":
    app.run()
