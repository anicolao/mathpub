from pathlib import Path
from mathpub.config import find_project
from tests.e2e.helpers.pdf_visual_helper import PDFVisualHelper

def test_physics_practice_worksheet_visual_regression(update_baselines):
    project = find_project()
    scenario_dir = Path(__file__).parent
    
    # Initialize the PDF Visual regression Helper
    helper = PDFVisualHelper(
        project,
        scenario_dir,
        update_baselines=update_baselines
    )
    
    # Compile and verify physics publication against seed 2026 variant A
    helper.verify_publication(
        publication_path=Path("publications/physics-practice.toml"),
        seed="2026",
        variant="A"
    )
    
    # Generate walkthrough documentation for visual checks
    helper.generate_markdown(title="Physics Practice Worksheet (Mechanics)")
