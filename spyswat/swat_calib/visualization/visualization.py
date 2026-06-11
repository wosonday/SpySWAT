import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from typing import Optional, List, Tuple, Dict


import logging
logger = logging.getLogger(__name__)

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 10



class SWATVisualization:
    def __init__(self, analysis):
        self.analysis = analysis
        self.project = analysis.project

    def plot_time_series(
            self,
            observed: pd.Series,
            simulated: pd.Series,
            title: str = "Observed vs Simulated",
            xlabel: str = "Time",
            ylabel: str = "Value",
            save_path: Optional[str] = None,
            show_stats: bool = True,
            figsize: Tuple[int, int] = (14, 6)
    ):
        """
        Plot observed vs simulated time series
        Args:
            observed: Observed data series
            simulated: Simulated data series
            title: Plot title
            xlabel: X-axis label
            ylabel: Y-axis label
            save_path: Path to save figure
            show_stats: Show statistics on plot
            figsize: Figure size
        """
        fig, ax = plt.subplots(figsize=figsize)
        # Plot data
        ax.plot(observed.index, observed.values,
                label='Observed', linewidth=2, color='#2E86AB', alpha=0.8)
        ax.plot(simulated.index, simulated.values,
                label='Simulated', linewidth=1.5, color='#A23B72',
                linestyle='--', alpha=0.7)

        # Add statistics if requested
        if show_stats:
            stats = self.analysis.calculate_statistics(observed, simulated)
            stats_text = (f"NSE = {stats['nse']:.3f}\n"
                          f"R2 = {stats['r2']:.3f}\n"
                          f"PBIAS = {stats['pbias']:.1f}%")

            ax.text(0.02, 0.98, stats_text,
                    transform=ax.transAxes,
                    verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8),
                    fontsize=10)
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.legend(loc='upper right', fontsize=11)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"Figure saved to {save_path}")

        plt.show()

    def plot_scatter(
            self,
            observed: pd.Series,
            simulated: pd.Series,
            title: str = "Observed vs Simulated",
            save_path: Optional[str] = None,
            show_stats: bool = True,
            figsize: Tuple[int, int] = (8, 8)
    ):
        """
        Scatter plot with 1:1 line

        Args:
            observed: Observed data
            simulated: Simulated data
            title: Plot title
            save_path: Path to save figure
            show_stats: Show statistics
            figsize: Figure size
        """
        fig, ax = plt.subplots(figsize=figsize)

        # Scatter plot
        ax.scatter(observed, simulated, alpha=0.5, s=30, color='#2E86AB')

        # 1:1 line
        min_val = min(observed.min(), simulated.min())
        max_val = max(observed.max(), simulated.max())
        ax.plot([min_val, max_val], [min_val, max_val],
                'r--', linewidth=2, label='1:1 Line')

        # Best fit line
        z = np.polyfit(observed, simulated, 1)
        p = np.poly1d(z)
        ax.plot(observed, p(observed),
                'g-', linewidth=2, alpha=0.7,
                label=f'Best Fit: y={z[0]:.2f}x+{z[1]:.2f}')

        # Statistics
        if show_stats:
            stats = self.analysis.calculate_statistics(observed, simulated)
            stats_text = (f"NSE = {stats['nse']:.3f}\n"
                          f"R2 = {stats['r2']:.3f}\n"
                          f"RMSE = {stats['rmse']:.2f}\n"
                          f"PBIAS = {stats['pbias']:.1f}%")

            ax.text(0.05, 0.95, stats_text,
                    transform=ax.transAxes,
                    verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8),
                    fontsize=10)

        ax.set_xlabel('Observed', fontsize=12)
        ax.set_ylabel('Simulated', fontsize=12)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.legend(loc='lower right', fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal', adjustable='box')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"Figure saved to {save_path}")

        plt.show()

    # ==================== Hydrograph Plots ====================

    def plot_hydrograph(
            self,
            reach_id: int,
            observed_name: Optional[str] = None,
            start_month: Optional[int] = None,
            end_month: Optional[int] = None,
            save_path: Optional[str] = None
    ):
        """
        Plot hydrograph for a specific reach

        Args:
            reach_id: Reach ID
            observed_name: Name of observed dataset (optional)
            start_month: Start month
            end_month: End month
            save_path: Path to save figure
        """
        # Get simulated data
        sim_df = self.project.output.read_reach(reach_id=reach_id)

        if start_month:
            sim_df = sim_df[sim_df['MON'] >= start_month]
        if end_month:
            sim_df = sim_df[sim_df['MON'] <= end_month]

        # Plot
        fig, ax = plt.subplots(figsize=(14, 6))

        ax.plot(sim_df['MON'], sim_df['FLOW_OUTcms'],
                label='Simulated', linewidth=2, color='#A23B72')

        # Add observed if available
        if observed_name:

            obs_data = self.project.get_observed_data(observed_name)

            obs_df = obs_data.df

            if start_month and end_month:

                obs_df = obs_df.iloc[start_month - 1:end_month]



            ax.plot(range(len(obs_df)), obs_df.iloc[:, 1],

                    label='Observed', linewidth=2, color='#2E86AB')



        ax.set_xlabel('Month', fontsize=12)

        ax.set_ylabel('Flow (m┬│/s)', fontsize=12)

        ax.set_title(f'Hydrograph - Reach {reach_id}', fontsize=14, fontweight='bold')

        ax.legend(loc='best', fontsize=11)

        ax.grid(True, alpha=0.3)



        plt.tight_layout()



        if save_path:

            plt.savefig(save_path, dpi=300, bbox_inches='tight')



        plt.show()



    # ==================== Sensitivity Analysis Plots ====================



    def plot_sensitivity(

            self,

            sensitivity_df: pd.DataFrame,

            metric: str = 'sensitivity_index',

            top_n: Optional[int] = None,

            title: str = "Parameter Sensitivity",

            save_path: Optional[str] = None,

            figsize: Tuple[int, int] = (10, 6)

    ):

        """

        Plot parameter sensitivity analysis results



        Args:

            sensitivity_df: DataFrame with sensitivity results

            metric: Metric column to plot

            top_n: Show only top N parameters

            title: Plot title

            save_path: Path to save figure

            figsize: Figure size

        """

        df = sensitivity_df.copy()



        if top_n:

            df = df.head(top_n)



        fig, ax = plt.subplots(figsize=figsize)



        colors = plt.cm.RdYlGn(np.linspace(0.2, 0.8, len(df)))



        ax.barh(df['parameter'], df[metric], color=colors)

        ax.set_xlabel(metric.replace('_', ' ').title(), fontsize=12)

        ax.set_ylabel('Parameter', fontsize=12)

        ax.set_title(title, fontsize=14, fontweight='bold')

        ax.grid(True, alpha=0.3, axis='x')



        plt.tight_layout()



        if save_path:

            plt.savefig(save_path, dpi=300, bbox_inches='tight')



        plt.show()



    def plot_morris_sensitivity(

            self,

            morris_results: Dict,

            save_path: Optional[str] = None,

            figsize: Tuple[int, int] = (10, 8)

    ):

        """

        Plot Morris sensitivity analysis results (mu* vs sigma)



        Args:

            morris_results: Results from morris_method

            save_path: Path to save figure

            figsize: Figure size

        """

        df = morris_results['morris_indices']



        fig, ax = plt.subplots(figsize=figsize)



        scatter = ax.scatter(df['mu_star'], df['sigma'],

                             s=200, alpha=0.6, c=df['mu_star'],

                             cmap='RdYlGn')



        # Add labels

        for idx, row in df.iterrows():

            ax.annotate(row['parameter'],

                        (row['mu_star'], row['sigma']),

                        xytext=(5, 5), textcoords='offset points',

                        fontsize=9)



        ax.set_xlabel('╬╝* (Mean Elementary Effect)', fontsize=12)

        ax.set_ylabel('╧â (Standard Deviation)', fontsize=12)

        ax.set_title('Morris Sensitivity Analysis', fontsize=14, fontweight='bold')

        ax.grid(True, alpha=0.3)



        plt.colorbar(scatter, label='╬╝*', ax=ax)

        plt.tight_layout()



        if save_path:

            plt.savefig(save_path, dpi=300, bbox_inches='tight')



        plt.show()



    # ==================== Calibration Plots ====================



    def plot_calibration_history(

            self,

            calibration_results: Dict,

            save_path: Optional[str] = None,

            figsize: Tuple[int, int] = (12, 6)

    ):

        """

        Plot calibration optimization history



        Args:

            calibration_results: Results from calibration.optimize()

            save_path: Path to save figure

            figsize: Figure size
        """
        history = calibration_results['history']

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

        # Objective value over iterations
        ax1.plot(history['iteration'], history['objective_value'],
                 linewidth=2, color='#2E86AB')
        ax1.set_xlabel('Iteration', fontsize=12)
        ax1.set_ylabel('Objective Value', fontsize=12)
        ax1.set_title('Optimization Convergence', fontsize=13, fontweight='bold')
        ax1.grid(True, alpha=0.3)

        # Parameter evolution
        param_cols = [col for col in history.columns
                      if col not in ['iteration', 'objective_value']]

        for col in param_cols:
            ax2.plot(history['iteration'], history[col],
                     label=col, linewidth=1.5, alpha=0.7)

        ax2.set_xlabel('Iteration', fontsize=12)
        ax2.set_ylabel('Parameter Value', fontsize=12)
        ax2.set_title('Parameter Evolution', fontsize=13, fontweight='bold')
        ax2.legend(loc='best', fontsize=9)
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        plt.show()

    def plot_parameter_correlation(
            self,
            batch_results: pd.DataFrame,
            params: Optional[List[str]] = None,
            save_path: Optional[str] = None,
            figsize: Tuple[int, int] = (10, 8)
    ):
        """
        Plot correlation matrix for parameters and metrics

        Args:
            batch_results: Results from batch_statistics
            params: List of parameters to include (None = all)
            save_path: Path to save figure
            figsize: Figure size
        """
        if params is None:
            # Get all parameter columns
            params = [col for col in batch_results.columns
                      if col not in ['run_id', 'mean', 'std']]

        # Calculate correlation
        corr = batch_results[params].corr()

        # Plot heatmap
        fig, ax = plt.subplots(figsize=figsize)

        sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm',
                    center=0, square=True, ax=ax,
                    cbar_kws={'label': 'Correlation'})

        ax.set_title('Parameter Correlation Matrix',
                     fontsize=14, fontweight='bold')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        plt.show()
