//
//  PortalysisApp.swift
//  Portalysis
//
//  Created by Lapo Elisacci on 18/08/2026.
//

import SwiftUI
import CoreData

@main
struct PortalysisApp: App {
    let persistenceController = PersistenceController.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.managedObjectContext, persistenceController.container.viewContext)
        }
    }
}
