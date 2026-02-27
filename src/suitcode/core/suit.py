import workspace


class Suit:
    @classmethod
    def open_workspace(cls, project_path: str) -> workspace.Workspace:
        pass
    
    @classmethod
    def close_workspace(cls, handle: workspace.WorkspaceHandle) -> workspace.Workspace:
        pass

    