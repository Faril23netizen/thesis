"""
Rule-Based Agent — Simple threshold-based controller
====================================================
Baseline controller using fixed pH and temperature thresholds.
No learning, no adaptation — pure rule-based logic.

This mirrors the safety_action() function from Pico firmware (main.c).

Original code from backup_v1_control_system/main/real/run_real.py
"""

# Action constants (aerator control levels)
ACTION_OFF  = 0
ACTION_LOW  = 1
ACTION_MED  = 2
ACTION_HIGH = 3


class RuleBasedAgent:
    """
    Simple rule-based controller using fixed thresholds.
    
    This is the baseline for comparison with FQL and DQN.
    No learning, no Q-table, just hardcoded rules.
    
    Exact mirror of safety_action() in Pico main.c firmware.
    """
    
    def __init__(self):
        """Initialize rule-based agent."""
        self.name = "Rule-Based"
        self.total_steps = 0
    
    def predict_action(self, pH: float, T: float) -> int:
        """
        Predict aerator action based on pH and temperature thresholds.
        
        Rules (mirrors Pico firmware safety_action()):
        - CRITICAL: pH < 6.0 or pH > 9.5 or T > 35°C → ACTION_HIGH (3)
        - WARNING:  pH < 6.5 or pH > 8.5 or T > 30°C → ACTION_MED (2)
        - NORMAL:   Otherwise → ACTION_LOW (1)
        
        Args:
            pH: Water pH value (6.0 - 9.5)
            T: Water temperature in Celsius (20 - 35)
        
        Returns:
            Action level (0=OFF, 1=LOW, 2=MED, 3=HIGH)
        """
        self.total_steps += 1
        
        # Critical conditions
        if pH < 6.0 or pH > 9.5 or T > 35.0:
            return ACTION_HIGH
        
        # Warning conditions
        if pH < 6.5 or pH > 8.5 or T > 30.0:
            return ACTION_MED
        
        # Normal conditions
        return ACTION_LOW
    
    def update(self, pH: float, T: float, predicted: int, actual: int):
        """
        No learning for rule-based agent.
        This method exists for API compatibility with FQL and DQN.
        """
        pass
    
    def get_stats(self) -> dict:
        """Get agent statistics."""
        return {
            "name": self.name,
            "total_steps": self.total_steps,
            "learning": False,
        }


def rule_based_action(pH: float, T: float) -> int:
    """
    Standalone function for rule-based action prediction.
    Exact mirror of safety_action() in Pico main.c.
    
    Args:
        pH: Water pH value
        T: Water temperature in Celsius
    
    Returns:
        Action level (0=OFF, 1=LOW, 2=MED, 3=HIGH)
    """
    if pH < 6.0 or pH > 9.5 or T > 35.0:
        return ACTION_HIGH
    if pH < 6.5 or pH > 8.5 or T > 30.0:
        return ACTION_MED
    return ACTION_LOW


def nh3_fraction(pH: float, T: float) -> float:
    """
    Calculate fraction of total ammonia in unionized (toxic) NH3 form.
    
    Uses temperature-dependent pKa calculation.
    
    Args:
        pH: Water pH value
        T: Water temperature in Celsius
    
    Returns:
        Fraction of NH3 (0.0 to 1.0)
    """
    pka = 0.09018 + 2729.92 / (T + 273.15)
    return 1.0 / (1.0 + 10 ** (pka - pH))


def calculate_nh3_percentage(pH: float, T: float) -> float:
    """
    Calculate NH3 percentage from pH and temperature.
    
    Args:
        pH: Water pH value
        T: Water temperature in Celsius
    
    Returns:
        NH3 percentage (0.0 to 100.0)
    """
    return nh3_fraction(pH, T) * 100.0


# Action cost for reward calculation
ACTION_COST = {
    ACTION_OFF:  0.0,
    ACTION_LOW:  0.3,
    ACTION_MED:  0.6,
    ACTION_HIGH: 1.0,
}
