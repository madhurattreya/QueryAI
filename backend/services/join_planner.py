import pandas as pd
from backend.services.relationship_engine import RelationshipEngine
import backend.config as config

class JoinPlanner:
    def __init__(self):
        self.rel_engine = RelationshipEngine()

    def find_required_tables(self, parsed_query) -> list:
        """
        Determines which tables contain the columns referenced in the parsed query.
        """
        referenced_columns = []
        if parsed_query.filters:
            for f in parsed_query.filters:
                referenced_columns.append(f["column"])
        if parsed_query.aggregations:
            for a in parsed_query.aggregations:
                referenced_columns.append(a["column"])
        if parsed_query.sorting:
            for s in parsed_query.sorting:
                referenced_columns.append(s["column"])
        
        # Also check columns from execution plan
        groupby = parsed_query.execution_plan.get("groupby", [])
        referenced_columns.extend(groupby)
        
        # Entities columns
        matched_cols = parsed_query.entities.get("matched_columns", [])
        referenced_columns.extend(matched_cols)

        # Make unique
        ref_cols_set = set(referenced_columns)

        # Map columns to tables
        required_tables = set()
        for col in ref_cols_set:
            for table_name, df in config.datasets.items():
                if col in df.columns:
                    required_tables.add(table_name)
                    break
        return list(required_tables)

    def find_join_path(self, start_table: str, target_table: str, graph: dict, visited=None) -> list:
        """
        Finds a join path (list of relationship edges) between start_table and target_table using BFS/DFS.
        """
        if visited is None:
            visited = set()
            
        if start_table == target_table:
            return []
            
        visited.add(start_table)
        
        if start_table not in graph:
            return None
            
        # BFS Queue for shortest path
        queue = [[(start_table, None, None)]]
        visited = {start_table}
        
        while queue:
            path = queue.pop(0)
            node = path[-1][0]
            
            if node == target_table:
                # Format the path into list of hops
                hops = []
                for idx in range(len(path) - 1):
                    src = path[idx][0]
                    dst = path[idx+1][0]
                    edge = path[idx+1][1]
                    hops.append({
                        "from_table": src,
                        "to_table": dst,
                        "from_col": edge["from_col"],
                        "to_col": edge["to_col"],
                        "type": edge["type"]
                    })
                return hops
                
            for edge in graph.get(node, []):
                neighbor = edge["to_table"]
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append((neighbor, edge))
                    queue.append(new_path)
                    
        return None

    def plan_and_join_datasets(self, parsed_query) -> tuple:
        """
        Finds the required tables, builds the join plan, executes the joins to return a single merged DataFrame.
        Returns: (merged_df, pandas_code_expression_str, matched_tables)
        """
        tables = self.find_required_tables(parsed_query)
        if not tables:
            return None, "", []
            
        if len(tables) == 1:
            # Single table, no join needed
            return config.datasets[tables[0]], f"{tables[0]}.copy()", tables

        # Multi-table query. Build the join plan.
        graph = self.rel_engine.get_relationship_graph()
        
        # We start with the first table and join others
        start_table = tables[0]
        merged_df = config.datasets[start_table].copy()
        code_parts = [f"{start_table}.copy()"]
        joined_tables = {start_table}
        
        # Attempt to join each other table
        for table in tables[1:]:
            if table in joined_tables:
                continue
                
            # Find path from any already joined table to the new table
            path = None
            for joined in joined_tables:
                path = self.find_join_path(joined, table, graph)
                if path:
                    break
                    
            if not path:
                # No path found, fallback to cross join or skip
                continue
                
            # Execute path merges
            for hop in path:
                dst = hop["to_table"]
                if dst in joined_tables:
                    continue
                    
                df_to_join = config.datasets[dst]
                left_on = hop["from_col"]
                right_on = hop["to_col"]
                
                # Check for suffix collision
                overlap_cols = set(merged_df.columns).intersection(set(df_to_join.columns)) - {left_on, right_on}
                suffixes = ('', f'_{dst}') if overlap_cols else ('_x', '_y')
                
                merged_df = merged_df.merge(
                    df_to_join,
                    left_on=left_on,
                    right_on=right_on,
                    how="left",
                    suffixes=suffixes
                )
                
                # Update code expression
                code_parts.append(
                    f".merge({dst}, left_on='{left_on}', right_on='{right_on}', how='left', suffixes={suffixes})"
                )
                joined_tables.add(dst)
                
        final_code = "".join(code_parts)
        return merged_df, final_code, list(joined_tables)
