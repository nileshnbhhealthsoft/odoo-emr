/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { AccordionItem } from "@web/core/dropdown/accordion_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const favoriteMenuRegistry = registry.category("favoriteMenu");

export class AdvancedFilterFavoriteItem extends Component {
    static template = "advanced_filter_engine.AdvancedFilterFavoriteItem";
    static components = { AccordionItem };
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.notificationService = useService("notification");
        this.orm = useService("orm");
        this.state = useState({
            filters: [],
            isLoading: true,
            modelLabel: "",
        });

        onWillStart(async () => {
            await this.loadFilters();
        });
    }

    get resModel() {
        return this.env.searchModel?.resModel || false;
    }

    get hasFilters() {
        return this.state.filters.length > 0;
    }

    async loadFilters() {
        if (!this.resModel) {
            this.state.isLoading = false;
            return;
        }
        this.state.isLoading = true;
        try {
            const [filters, modelInfo] = await Promise.all([
                this.orm.call("advanced.filter", "get_filters_for_model", [this.resModel]),
                this.orm.searchRead(
                    "ir.model",
                    [["model", "=", this.resModel]],
                    ["name"],
                    { limit: 1 }
                ),
            ]);
            this.state.filters = filters;
            this.state.modelLabel = modelInfo[0]?.name || this.resModel;
        } catch {
            this.state.filters = [];
            this.state.modelLabel = this.resModel;
        } finally {
            this.state.isLoading = false;
        }
    }

    async applyFilter(filter) {
        try {
            const action = await this.orm.call("advanced.filter", "action_apply_filter", [[filter.id]]);
            await this.actionService.doAction(action);
        } catch (error) {
            this.notificationService.add(
                error.message || _t("The advanced filter could not be applied."),
                { type: "danger" }
            );
        }
    }

    async editFilter(filter) {
        try {
            const action = await this.orm.call("advanced.filter", "action_open_filter_form", [[filter.id]]);
            await this.actionService.doAction(action, {
                onClose: async () => this.loadFilters(),
            });
        } catch (error) {
            this.notificationService.add(
                error.message || _t("The advanced filter form could not be opened."),
                { type: "danger" }
            );
        }
    }

    async deleteFilter(filter) {
        if (!filter.is_owner) {
            return;
        }
        try {
            const result = await this.orm.call("advanced.filter", "delete_filter", [filter.id]);
            if (result?.error) {
                this.notificationService.add(result.error, { type: "danger" });
                return;
            }
            await this.loadFilters();
        } catch (error) {
            this.notificationService.add(
                error.message || _t("The advanced filter could not be deleted."),
                { type: "danger" }
            );
        }
    }

    async createFilter() {
        if (!this.resModel) {
            return;
        }
        try {
            const action = await this.orm.call("advanced.filter", "action_create_for_model", [this.resModel]);
            await this.actionService.doAction(action);
        } catch (error) {
            this.notificationService.add(
                error.message || _t("The advanced filter form could not be opened."),
                { type: "danger" }
            );
        }
    }

    async openManager() {
        await this.actionService.doAction("advanced_filter_engine.action_advanced_filter", {
            additionalContext: {
                search_default_my_filters: 1,
            },
        });
    }
}

favoriteMenuRegistry.add(
    "advanced-filter-favorite-item",
    {
        Component: AdvancedFilterFavoriteItem,
        groupNumber: 2,
        isDisplayed: (env) => Boolean(env.searchModel?.resModel && env.searchModel?.searchViewFields),
    },
    { sequence: 20 }
);
